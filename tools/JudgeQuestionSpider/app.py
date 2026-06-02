import os
import base64
import traceback
import shutil
import cv2
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS
import ddddocr

app = Flask(__name__)
CORS(app)  # 允許跨域請求

# 初始化 ddddocr
try:
    ocr = ddddocr.DdddOcr(
        show_ad=False, 
        import_onnx_path="NtustCourseJudge_para121755_dsunknown_acc0.9921875_ep166_step24000_2026-06-02-05-04-52.onnx", 
        charsets_path="charsets.json"
    )
except Exception as e:
    print(f"[嚴重錯誤] ddddocr 初始化失敗: {e}")
    ocr = None

# 定義並初始化目錄結構
BASE_DIRS = {
    'correct_main': 'correct',
    'correct_orig': os.path.join('correct', 'original'),
    'wrong_main': 'wrong',
    'wrong_orig': os.path.join('wrong', 'original'),
    'temp': 'temp'  # 用於暫存尚未知道對錯的圖片
}

for name, folder in BASE_DIRS.items():
    try:
        os.makedirs(folder, exist_ok=True)
    except Exception as e:
        print(f"[錯誤] 無法建立目錄 {folder}: {e}")

def preprocess_image(image_bytes):
    """
    影像前處理：去除雜訊線、二值化、Dilation (膨脹) 處理
    """
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            print("[警告] OpenCV 無法解碼圖片 bytes，將使用原始圖片進行辨識")
            return image_bytes

        # 1. 去除雜訊線（非黑色保留成白色）
        lower_black = np.array([0, 0, 0], dtype=np.uint8)
        upper_black = np.array([40, 40, 40], dtype=np.uint8)
        black_mask = cv2.inRange(img, lower_black, upper_black)
        
        processed = np.ones_like(img) * 255
        processed[black_mask > 0] = [0, 0, 0]

        # 2. 轉成單色圖
        gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)

        # 3. Dilation (膨脹) 處理
        kernel = np.ones((2, 2), np.uint8)
        dilated = cv2.dilate(binary, kernel, iterations=1)

        # 反轉回白底黑字
        final_img = cv2.bitwise_not(dilated)

        _, encoded_img = cv2.imencode('.png', final_img)
        return encoded_img.tobytes()
    except Exception as e:
        print(f"[影像處理異常] {e}，將降級使用原始圖片")
        print(traceback.format_exc())
        return image_bytes


@app.route('/predict', methods=['POST'])  # 修正：method -> methods
def predict():
    try:
        if not ocr:
            return jsonify({'error': '後端辨識引擎 (ddddocr) 未成功初始化'}), 500

        data = request.json or {}
        img_base64 = data.get('image')
        timestamp = data.get('timestamp')

        if not img_base64 or not timestamp:
            return jsonify({'error': '缺少必要參數 image 或 timestamp'}), 400

        # 處理 base64 標頭
        if ',' in img_base64:
            img_base64 = img_base64.split(',')[1]
        
        try:
            raw_img_bytes = base64.b64decode(img_base64)
        except Exception as e:
            return jsonify({'error': f'Base64 解碼失敗: {str(e)}'}), 400

        # 1. 儲存原始圖片到 temp
        orig_temp_path = os.path.join(BASE_DIRS['temp'], f"orig_{timestamp}.png")
        with open(orig_temp_path, 'wb') as f:
            f.write(raw_img_bytes)

        # 2. 影像前處理
        processed_img_bytes = preprocess_image(raw_img_bytes)

        # 3. 儲存處理後的圖片到 temp
        proc_temp_path = os.path.join(BASE_DIRS['temp'], f"proc_{timestamp}.png")
        with open(proc_temp_path, 'wb') as f:
            f.write(processed_img_bytes)

        # 4. 使用 ddddocr 預測
        try:
            prediction = ocr.classification(processed_img_bytes)
            prediction = prediction.strip().upper()  # 移除空白並轉大寫
        except Exception as e:
            print(f"[辨識核心錯誤] {e}")
            return jsonify({'error': f'ddddocr 辨識過程發生錯誤: {str(e)}'}), 500

        print(f"[成功] 時間戳: {timestamp} -> 預測結果: {prediction}")
        return jsonify({
            'timestamp': timestamp,
            'prediction': prediction
        })

    except Exception as e:
        # 捕捉任何漏網的未知異常，列印完整錯誤日誌，確保服務不崩潰
        print(f"[未知內部錯誤] {e}")
        print(traceback.format_exc())
        return jsonify({'error': f'系統內部錯誤: {str(e)}'}), 500


@app.route('/report', methods=['POST'])  # 修正：method -> methods
def report():
    try:
        data = request.json or {}
        timestamp = data.get('timestamp')
        prediction = data.get('prediction')
        status = data.get('status')  # 'correct' 或 'wrong'

        if not timestamp or not prediction or not status:
            return jsonify({'error': '缺少回報必要參數'}), 400

        if status not in ['correct', 'wrong']:
            return jsonify({'error': '不合法的狀態值，必須為 correct 或 wrong'}), 400

        orig_temp_path = os.path.join(BASE_DIRS['temp'], f"orig_{timestamp}.png")
        proc_temp_path = os.path.join(BASE_DIRS['temp'], f"proc_{timestamp}.png")

        # 檢查暫存檔案是否存在
        if not os.path.exists(orig_temp_path) or not os.path.exists(proc_temp_path):
            return jsonify({'error': f'找不到對應時間戳 {timestamp} 的暫存檔案，可能已被處理過或請求順序有誤'}), 404

        # 根據對錯選擇目標路徑
        if status == 'correct':
            target_main_dir = BASE_DIRS['correct_main']
            target_orig_dir = BASE_DIRS['correct_orig']
        else:
            target_main_dir = BASE_DIRS['wrong_main']
            target_orig_dir = BASE_DIRS['wrong_orig']

        final_filename = f"{prediction}_{timestamp}.png"

        # 執行檔案移動與錯誤保護
        try:
            shutil.move(proc_temp_path, os.path.join(target_main_dir, final_filename))
            shutil.move(orig_temp_path, os.path.join(target_orig_dir, final_filename))
        except Exception as e:
            return jsonify({'error': f'歸檔移動檔案時失敗: {str(e)}'}), 500

        print(f"[回報] 驗證碼 [{prediction}] 判定為 [{status}]，已成功歸檔。")
        return jsonify({'message': f'結果歸檔成功，分類為: {status}'})

    except Exception as e:
        print(f"[未知回報錯誤] {e}")
        print(traceback.format_exc())
        return jsonify({'error': f'系統內部錯誤: {str(e)}'}), 500


if __name__ == '__main__':
    # 啟動後端服務
    app.run(host='0.0.0.0', port=7778, debug=True)
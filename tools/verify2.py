import os
import re
import time
import base64
import hashlib
import itertools
import subprocess
import ddddocr
from PIL import Image

# ==========================================
# 0. 自動建立所需的資料夾
# ==========================================
directories = ['correct', 'wrong', 'wrong_to_correct', 'captchas']
for d in directories:
    if not os.path.exists(d):
        os.makedirs(d)

# ==========================================
# 1. 載入自訂訓練好的 ONNX 模型 (已修改)
# ==========================================
# 💡 請將 'your_model_name.onnx' 替換為你剛訓練出來的真實檔名 (例如: ntest_new_mail_captcha_xxxx.onnx)
model_path = "NtustNewMailCaptcha.onnx" 
charset_path = "charsets.json"

if not os.path.exists(model_path):
    raise FileNotFoundError(f"❌ 找不到自訂模型檔案 '{model_path}'，請先將訓練好的 .onnx 檔複製到此目錄！")

print(f"🚀 正在載入自訂 ONNX 模型: {model_path} ...")

# 帶入自訂的 det_model_path (若沒訓練偵測則不填) 與 ocr_model_path
ocr = ddddocr.DdddOcr(
    det=False, 
    ocr=True,
    import_onnx_path=model_path,    # 載入自訂權重
    charsets_path=charset_path,     # 載入對應的字元集映射
    show_ad=False                   # 關閉廣告
)

# ==========================================
# 2. 暴力修正函數 (itertools 濃縮版)
# ==========================================
def find_correct(predict, hash_id, img):
    target_tokens = ['0', '6', '9']
    
    # 找出預測字串中，是 0, 6, 9 的位置索引
    positions_needs_switch = [i for i, char in enumerate(predict) if char in target_tokens]

    # 如果沒有需要替換的字元，或者長度不是 5，就直接放棄
    if not positions_needs_switch or len(predict) != 5:
        return

    print(f"[修正模式] 發現易混淆數字，啟動組合替換...")

    # itertools.product 會自動產生所有的排列組合 (例如 3^2 = 9 種)
    for combo in itertools.product(target_tokens, repeat=len(positions_needs_switch)):
        predict_list = list(predict)
        
        # 將這組排列組合塞回對應的位置
        for pos, new_char in zip(positions_needs_switch, combo):
            predict_list[pos] = new_char
            
        new_predict = "".join(predict_list)
        
        # 呼叫 PHP 腳本驗證
        result = subprocess.getstatusoutput(f'php tools/spider.php {hash_id} {new_predict}')[1]
        print(f"  > 嘗試 {new_predict} -> {result}")
        
        if result == "true":
            new_filename = f'wrong_to_correct/{new_predict}_{hash_id}.png'
            img.save(new_filename)
            print(f'🎉 成功救回！正確答案是: {new_predict}')
            return

# ==========================================
# 3. 主迴圈：抓圖 -> 預測 -> 驗證 -> 儲存
# ==========================================
correct_count = 0
total_count = 0

# 設定你要抓取的總數量
for i in range(100):
    total_count += 1
    print(f'--- Step: {i} ---')
    
    # [步驟 A] 抓取圖片與 Hash
    time_get = time.time()
    hash_id = subprocess.getstatusoutput('php tools/spider.php')[1]
    print(f'獲取圖片耗時: {time.time() - time_get:.2f}s')
    
    # [步驟 B] 找出剛剛 PHP 存進 captchas/ 的圖片路徑
    try:
        raw_hash = base64.b64decode(hash_id).decode('utf-8')
        safe_filename = hashlib.md5(raw_hash.encode('utf-8')).hexdigest()
        file_name = f'captchas/{safe_filename}.gif'
    except Exception as e:
        print(f"Hash 解析失敗，跳過此圖。錯誤: {e}")
        continue

    if not os.path.exists(file_name):
        print(f"找不到圖片檔案: {file_name}，可能抓圖失敗，跳過。")
        continue

    with open(file_name, 'rb') as f:
        img_bytes = f.read()

    # [步驟 C] 呼叫新模型預測
    time_predict = time.time()
    predict = ocr.classification(img_bytes)
    
    # 🎯 終極防護盾：過濾掉 Windows 不允許的特殊符號與換行，通通替換成底線
    # predict = re.sub(r'[^a-zA-Z0-9]', "_", predict).strip()
    
    print(f'預測耗時: {time.time() - time_predict:.2f}s')

    # [步驟 D] 對台科大伺服器對答案
    time_verify = time.time()
    correct_prediction = subprocess.getstatusoutput(f'php tools/spider.php {hash_id} {predict}')[1]
    print(f'驗證耗時: {time.time() - time_verify:.2f}s')

    print(f'預測結果: {predict}')
    print(f'伺服器回傳: {correct_prediction}')

    # [步驟 E] 儲存與分類
    img = Image.open(file_name)
    
    if correct_prediction == 'true':
        correct_count += 1
        img.save(f'correct/{predict}_{hash_id}.png')
    else:
        img.save(f'wrong/{predict}_{hash_id}.png')
        find_correct(predict, hash_id, img)

    # 【重要防呆】在 Windows 刪除圖片前，必須先呼叫 close 釋放資源
    img.close()
    os.remove(file_name)

    print(f'目前自訂模型準確率 (Acc): {correct_count / total_count:.4f}\n')

(function () {
    'use strict';

    const BACKEND_URL = 'http://localhost:7778';
    const CHECK_INTERVAL = 500; // 每 500 毫秒掃描一次
    
    // ================= 設定抓圖次數上限 =================
    const MAX_CAPTCHAS_TO_FETCH = 5; // 總共允許抓取幾張驗證碼圖片（設為 0 代表不限制）
    // ===================================================

    // 輔助函數：將 <img> 轉換成 Base64
    function getBase64Image(imgKey) {
        const img = document.getElementById(imgKey);
        if (!img || !img.complete || img.naturalWidth === 0) return null;
        
        const canvas = document.createElement("canvas");
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0);
        return canvas.toDataURL("image/png");
    }

    const timer = setInterval(() => {
        const errorSummary = document.querySelector('.validation-summary-errors');
        const captchaImg = document.getElementById('captchaImage');

        if (errorSummary && captchaImg && captchaImg.complete && captchaImg.naturalWidth > 0) {
            clearInterval(timer); // 滿足條件，停止掃描
            handleWorkflow(errorSummary);
        }
    }, CHECK_INTERVAL);

    function handleWorkflow(errorSummary) {
        const errorText = errorSummary.textContent || "";
        const hasCaptchaError = errorText.includes("圖形驗證碼有誤");

        // 取出上一輪發送的預測資訊
        const lastTimestamp = localStorage.getItem('last_captcha_timestamp');
        const lastPrediction = localStorage.getItem('last_captcha_prediction');

        if (lastTimestamp && lastPrediction) {
            const status = hasCaptchaError ? 'wrong' : 'correct';
            reportResult(lastTimestamp, lastPrediction, status);
            
            localStorage.removeItem('last_captcha_timestamp');
            localStorage.removeItem('last_captcha_prediction');
        }

        // --- 檢查抓圖次數 ---
        let currentFetchCount = parseInt(localStorage.getItem('captcha_fetch_count') || '0', 10);
        console.log(`[目前狀態] 當前已抓圖次數: ${currentFetchCount} / ${MAX_CAPTCHAS_TO_FETCH}`);
        
        if (MAX_CAPTCHAS_TO_FETCH > 0 && currentFetchCount >= MAX_CAPTCHAS_TO_FETCH) {
            console.warn(`[停止] 已達到最大抓圖張數限制 (${MAX_CAPTCHAS_TO_FETCH} 張)，自動腳本終止。`);
            // 為了讓你以後手動點開還能用，我們在這裡不清空，你可以之後手動在 Console 執行 localStorage.clear()
            // 或者維持讓它停住，直到你關閉分頁
            return;
        }

        // 繼續處理當前驗證碼
        processCurrentCaptcha();
    }

    function reportResult(timestamp, prediction, status) {
        fetch(`${BACKEND_URL}/report`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                timestamp: timestamp,
                prediction: prediction,
                status: status
            })
        })
        .then(res => res.json())
        .then(data => {
            console.log('結果回報成功:', data);
            // 【核心修正點】：移除了原本 if (status === 'correct') { removeItem } 的歸零邏輯！
            // 不管對錯，抓圖計數都繼續累積，直到衝到上限為止。
        })
        .catch(err => console.error('結果回報失敗:', err));
    }

    // 使用 async/await 徹底掌控非同步順序
    async function processCurrentCaptcha() {
        const base64Data = getBase64Image('captchaImage');
        if (!base64Data) {
            console.error("無法取得驗證碼圖片 Base64");
            return;
        }

        const currentTimestamp = Math.floor(Date.now() / 1000).toString();

        // 1. 在發送請求之前，先同步將計數器加 1 寫入 localStorage
        let currentFetchCount = parseInt(localStorage.getItem('captcha_fetch_count') || '0', 10);
        currentFetchCount++;
        localStorage.setItem('captcha_fetch_count', currentFetchCount.toString());
        console.log(`[同步計數] 已登記準備發送第 ${currentFetchCount} 張圖的請求...`);

        try {
            // 2. 精準等待後端辨識結果
            const response = await fetch(`${BACKEND_URL}/predict`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    image: base64Data,
                    timestamp: currentTimestamp
                })
            });

            const data = await response.json();

            if (data.prediction) {
                // 3. 辨識成功，將預測資訊同步寫入快取
                localStorage.setItem('last_captcha_timestamp', currentTimestamp);
                localStorage.setItem('last_captcha_prediction', data.prediction);

                // 4. 填入驗證碼並立刻同步送出表單
                const captchaInput = document.getElementById('captchaInput');
                const form = document.querySelector('form');
                
                if (captchaInput && form) {
                    captchaInput.value = data.prediction;
                    console.log(`自動填入驗證碼: ${data.prediction}，正在提交表單...`);
                    form.submit();
                }
            } else {
                console.error("後端辨識失敗，從計數器扣除此次機會", data.error);
                rollbackCount();
            }
        } catch (err) {
            console.error("請求辨識 API 發生網路錯誤，從計數器扣除此次機會", err);
            rollbackCount();
        }
    }

    // 輔助函數：如果請求失敗，把預扣的次數加回來
    function rollbackCount() {
        let currentFetchCount = parseInt(localStorage.getItem('captcha_fetch_count') || '1', 10);
        localStorage.setItem('captcha_fetch_count', Math.max(0, currentFetchCount - 1).toString());
    }
})();
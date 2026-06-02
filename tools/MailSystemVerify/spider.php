<?php

// ==========================================
// 1. 抓圖函數 (先抓真實 CaptCode，再抓圖)
// ==========================================
function fetch() {
    // [第一階段] 去登入頁面挖出真實的 CaptCode
    $curl1 = curl_init();
    curl_setopt_array($curl1, array(
        CURLOPT_URL => 'https://mail.ntust.edu.tw/cgi-bin/login?index=1',
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_SSL_VERIFYPEER => false,
        CURLOPT_SSL_VERIFYHOST => false,
        CURLOPT_USERAGENT => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36'
    ));
    $html = curl_exec($curl1);
    

    // 用正規表達式挖出隱藏在 HTML 裡面的 CaptCode
    if (!preg_match('/name="CaptCode"\s+value="(\d+)"/i', $html, $matches)) {
        die("抓圖失敗！在網頁中找不到 CaptCode，伺服器可能擋下連線了。");
    }
    $real_capt_code = $matches[1];

    // [第二階段] 拿著真實的 CaptCode 去要圖片
    $timestamp = time();
    $url = "https://mail.ntust.edu.tw/cgi-bin/gen_capt?cmd=getim&id=LOGIN&code={$real_capt_code}&m={$timestamp}";

    $curl2 = curl_init();
    curl_setopt_array($curl2, array(
        CURLOPT_URL => $url,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_SSL_VERIFYPEER => false,
        CURLOPT_SSL_VERIFYHOST => false,
        CURLOPT_USERAGENT => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36'
    ));
    $response2 = curl_exec($curl2);
    

    // 確認我們拿到的是不是 GIF 圖片 (GIF 開頭會是 GIF87a 或 GIF89a)
    if (!str_starts_with($response2, 'GIF')) {
        die("抓圖失敗！伺服器回傳的不是圖片，請把檔案當純文字打開檢查。");
    }

    $base64_image = base64_encode($response2);
    $dataUri = 'data:image/gif;base64,' . $base64_image;

    $result = new stdClass();
    $result->dataUri = $dataUri;
    
    // 我們的 Hash 就是這個真實的 CaptCode，把它轉成 Base64 傳給主程式
    $result->captcha = base64_encode($real_capt_code); 

    return $result;
}

// ==========================================
// 2. 儲存圖片函數
// ==========================================
function base64_to_jpeg($base64_string, $output_file) {
    $ifp = fopen( "./captchas/" . $output_file, 'wb' );
    $data = explode( ',', $base64_string );
    fwrite( $ifp, base64_decode( $data[ 1 ] ) );
    fclose( $ifp );
    return $output_file;
}

// ==========================================
// 3. 驗證與登入函數
// ==========================================
function verify($hash, $ans) {
    $capt_code = base64_decode($hash);
    
    // 隨便亂填假帳號，我們本來就沒有要登入！
    $fake_account = 'training_bot@mail.ntust.edu.tw'; 
    $fake_password = 'fake_password_123';

    $post_data = http_build_query(array(
        'lang' => 'tw',
        'MAKE_CHALLENGE' => '1',
        'keep_days' => '7.5',
        'CHALLENGE' => '',
        'CLIENT_TOKEN' => '',
        'CaptCode' => $capt_code, 
        'USERID' => $fake_account,
        'PASSWD' => $fake_password,
        'CaptAns' => $ans 
    ));

    $curl = curl_init();
    curl_setopt_array($curl, array(
        CURLOPT_URL => 'https://mail.ntust.edu.tw/cgi-bin/login', 
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_CUSTOMREQUEST => 'POST',
        CURLOPT_POSTFIELDS => $post_data,
        CURLOPT_SSL_VERIFYPEER => false,
        CURLOPT_SSL_VERIFYHOST => false,
        CURLOPT_HTTPHEADER => array(
            'Content-Type: application/x-www-form-urlencoded',
        ),
        CURLOPT_USERAGENT => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36'
    ));

    $response = curl_exec($curl);
    
    // 【判斷邏輯大反轉】
    if (str_contains($response, '驗證碼錯誤') || str_contains($response, '圖形驗證碼不正確')) {
        // 伺服器抱怨驗證碼錯了 -> 代表 OCR 辨識失敗
        return false; 
    } elseif (str_contains($response, '輸入帳號或密碼錯誤')) {
        // 伺服器抱怨密碼錯了 -> 代表它已經認可了驗證碼 -> OCR 辨識大成功！
        return true; 
    }
    
    // 發生其他未知狀況 (例如網頁掛掉)
    return false; 
}

// ==========================================
// 4. CLI 啟動開關
// ==========================================
if (count($argv) >= 3) {
    $hash = $argv[1];
    $ans = $argv[2];
    $result = verify($hash, $ans);
    echo $result ? "true" : "false";
} else {
    $data = fetch();
    $safe_filename = md5(base64_decode($data->captcha)); 
    // 這次保證是 GIF，所以副檔名我幫你換回 .gif 了
    base64_to_jpeg($data->dataUri, $safe_filename . ".gif");
    
    echo $data->captcha; 
}
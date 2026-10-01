# HTTPS — Windows 서버 앞단에 nginx 두기

사내 CA 인증서로 `https://<호스트명>/` 을 연다. 제품 코드는 바꾸지 않는다 — nginx 가 443 에서 HTTPS 를 받아 뒤의 `http://127.0.0.1:8080` 으로 넘긴다.

```
왜 앞단인가   서버(uvicorn)는 HTTP 로만 뜨고, 서버 안의 작업자와 수집 스크립트가 http://127.0.0.1:8080 을 부른다.
             8080 을 HTTPS 로만 바꾸면 그 호출이 끊긴다(인증서는 호스트명으로 발급되고 127.0.0.1 은 그 이름이 아니다)
잰 범위       2 단계(인증서 파일 만들기)는 이 저장소의 개발 박스에서 시험용 CA 로 돌려 확인했다
             (Git for Windows 의 OpenSSL 1.1.1k · DER p7b · 서버 인증서가 사슬 맨 뒤에 있는 p7b).
             nginx 를 띄우는 3~8 단계는 돌려 보지 않았다
```

모든 명령은 **관리자 PowerShell 한 창**에서 순서대로. 앞에서 정한 변수(`$o`, `$ssl`)를 뒤에서 쓴다.

---

## 1. nginx 준비

nginx.org 의 download 페이지에서 «Stable version» 의 Windows zip 을 받아 `C:\nginx` 에 푼다(`C:\nginx\nginx.exe` 가 보이면 됨). 인증서 폴더를 만든다.

```powershell
New-Item -ItemType Directory -Force C:\nginx\conf\ssl
```

---

## 2. 인증서 파일 만들기 — pfx + p7b

```
cert.pfx  서버 인증서 + 개인키        -> 키와 서버 인증서를 여기서 꺼낸다
cert.p7b  CA 가 준 사슬(중간 인증서 등) -> 사슬을 여기서 꺼낸다
nginx 가 읽는 것  fullchain.crt (서버 인증서가 맨 앞, 뒤에 사슬) · server.key
```

받은 두 파일을 `C:\nginx\conf\ssl` 에 `cert.pfx`, `cert.p7b` 이름으로 넣는다.

```powershell
$o = "C:\Program Files\Git\usr\bin\openssl.exe"
```
```powershell
$ssl = "C:\nginx\conf\ssl"
```

다른 OpenSSL 의 설정 파일을 가리키는 환경 변수가 있으면 `libproviders.dll` 경고가 섞여 나온다. 이 창에서만 지운다(실측: 개발 박스에 있었고, 지우니 경고가 사라짐).

```powershell
Remove-Item Env:OPENSSL_CONF -ErrorAction SilentlyContinue
```

**① 개인키** — pfx 비밀번호를 묻는다.

```powershell
& $o pkcs12 -in "$ssl\cert.pfx" -nocerts -nodes -out "$ssl\server.key"
```

**② 서버 인증서**

```powershell
& $o pkcs12 -in "$ssl\cert.pfx" -clcerts -nokeys -out "$ssl\server.crt"
```

①②에서 `unsupported` · `RC2-40-CBC` 오류가 나면 명령 끝에 `-legacy` 를 붙인다(OpenSSL 3 일 때만 있는 옵션 — 1.1.1 은 이 오류가 안 난다).

**③ 사슬** — 오류 `unable to load PKCS7 object` 가 나면 파일이 DER 형식이다. 그때는 아래 두 번째 명령.

```powershell
& $o pkcs7 -print_certs -in "$ssl\cert.p7b" -out "$ssl\p7b_all.crt"
```
```powershell
& $o pkcs7 -inform DER -print_certs -in "$ssl\cert.p7b" -out "$ssl\p7b_all.crt"
```

**④ fullchain** — 서버 인증서를 맨 앞에, p7b 의 인증서 중 서버 인증서와 같은 것은 빼고 뒤에. p7b 안의 순서는 정해져 있지 않다. BOM 없는 ASCII 로 쓴다.

```powershell
$pem = "-----BEGIN CERTIFICATE-----[\s\S]+?-----END CERTIFICATE-----"; $leaf = [regex]::Match((Get-Content "$ssl\server.crt" -Raw), $pem).Value; $rest = [regex]::Matches((Get-Content "$ssl\p7b_all.crt" -Raw), $pem) | ForEach-Object { $_.Value } | Where-Object { ($_ -replace "\s","") -ne ($leaf -replace "\s","") }; Set-Content -Encoding ascii "$ssl\fullchain.crt" (($leaf, $rest | ForEach-Object { $_ }) -join "`n")
```

**⑤ 확인**

인증서 수 — 2 이상이면 사슬이 붙은 것.

```powershell
([regex]::Matches((Get-Content "$ssl\fullchain.crt" -Raw), "BEGIN CERTIFICATE")).Count
```

맨 앞 인증서 — `subject` · `Subject Alternative Name` 에 사람들이 주소창에 치는 이름(IP 로 접속하면 IP)이 있어야 한다.

```powershell
& $o x509 -in "$ssl\fullchain.crt" -noout -subject -ext subjectAltName
```

```
server.key 는 암호가 풀린 개인키다 — 이 폴더는 서버 관리자만 읽게. cert.pfx 는 끝난 뒤 다른 곳에 보관
```

---

## 3. `C:\nginx\conf\nginx.conf` 를 통째로 교체

`assy.example.local` 두 곳을 인증서의 호스트명으로 바꾼다.

```nginx
worker_processes  1;
events { worker_connections 1024; }

http {
    include       mime.types;
    default_type  application/octet-stream;
    sendfile      on;

    map $http_upgrade $connection_upgrade { default upgrade; '' close; }

    server {
        listen 80;
        server_name assy.example.local;
        return 301 https://$host$request_uri;
    }

    server {
        listen 443 ssl;
        server_name assy.example.local;

        ssl_certificate      C:/nginx/conf/ssl/fullchain.crt;
        ssl_certificate_key  C:/nginx/conf/ssl/server.key;
        ssl_protocols        TLSv1.2 TLSv1.3;

        client_max_body_size 0;

        location / {
            proxy_pass         http://127.0.0.1:8080;
            proxy_http_version 1.1;
            proxy_set_header   Host $host;
            proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header   X-Forwarded-Proto $scheme;
            proxy_set_header   Upgrade $http_upgrade;
            proxy_set_header   Connection $connection_upgrade;
            proxy_read_timeout 3600s;
            proxy_send_timeout 3600s;
            proxy_buffering    off;
        }
    }
}
```

```
client_max_body_size 0     nginx 기본은 1MB 넘는 요청을 막는다 — 표의 파일 올리기(POST /tables/{표}/upload)가 막히지 않게
Upgrade · Connection       실시간 갱신 웹소켓(/ws)을 넘긴다. 클라는 https 에서 스스로 wss 로 붙는다(client2/src/config.js WS_URL)
proxy_read_timeout 3600s   조용한 웹소켓이 60 초 만에 끊기지 않게
proxy_buffering off        CSV 내보내기처럼 흘려보내는 응답을 바로 넘긴다
80 번 server 블록          http 로 온 사람을 https 로. 80 을 다른 프로그램(IIS 등)이 쓰면 이 블록을 지운다
```

---

## 4. 검사하고 켜기

```powershell
cd C:\nginx
```

`syntax is ok` · `test is successful` 이 나와야 한다. `key values mismatch` 면 키와 맨 앞 인증서가 짝이 아니다 — 2 단계 ④ 의 순서를 본다.

```powershell
.\nginx.exe -t
```
```powershell
start nginx
```

설정을 고친 뒤 `.\nginx.exe -s reload` · 끌 때 `.\nginx.exe -s stop` (둘 다 `C:\nginx` 에서).

---

## 5. 방화벽 443

```powershell
New-NetFirewallRule -DisplayName "assy https" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow
```

---

## 6. 부팅 때 자동으로

Windows 용 nginx 는 서비스로 설치되지 않는다 — 작업 스케줄러에 «부팅 시 실행».

```powershell
Register-ScheduledTask -TaskName "nginx-assy" -Action (New-ScheduledTaskAction -Execute "C:\nginx\nginx.exe" -WorkingDirectory "C:\nginx") -Trigger (New-ScheduledTaskTrigger -AtStartup) -User "SYSTEM" -RunLevel Highest
```

---

## 7. 확인

```
다른 PC   브라우저로 https://<호스트명>/ — 자물쇠 · 그리드가 뜨고 실시간 갱신이 오면 웹소켓도 통한 것
          경고가 뜨면 = 그 PC 가 사내 CA 를 안 믿거나, 인증서에 그 이름이 없다
서버      아래가 200
```

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" https://<호스트명>/health
```

---

## 8. (선택) 8080 을 서버 안으로만

```
무엇      서버를 띄우기 전에 ASSY_API_HOST=127.0.0.1 — 8080 은 서버 PC 안에서만 받고, 다른 PC 는 https 로만 들어온다
          서버 안 작업자들은 127.0.0.1:8080 을 부르므로 그대로 돈다
하지 말 것 다른 PC 가 8080 을 직접 부르는 것이 있으면(그 PC 의 수집 스크립트 등) — 그 호출이 끊긴다
같이 볼 것 127.0.0.1 은 IPv4 만 받는다. 서버 PC 에서 `localhost:8080` 으로 부르는 것(브라우저 · 스크립트)은 Windows 가 ::1 을 먼저
          골라 안 붙거나, 페이지는 떠도 웹소켓이 CONNECTING 에 멈춘다(run_decoupled_app.py 의 기본 바인드 주석, 08-04 실측).
          서버 안에서는 127.0.0.1 로 부른다
같이      바탕화면 바로가기 · 즐겨찾기를 https://<호스트명>/ 으로
되돌리기   ASSY_API_HOST 를 지우고 재기동하면 기본 바인드로 — IPv4 · IPv6 전부를 받는 듀얼 스택(`process_supervisor.DUAL_STACK_HOST`,
          0.0.0.0 이 아니다 — 0.0.0.0 은 IPv4 만)
```

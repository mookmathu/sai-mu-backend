# สแกนคุณภาพโค้ด backend ด้วย SonarQube (รันในเครื่อง)

ต้องมี Docker Desktop (Windows) เปิดอยู่

1. เปิดเซิร์ฟเวอร์ SonarQube (รอ 1-3 นาที)
   ```powershell
   cd D:\sai_mu_backend
   docker compose -f docker-compose.sonar.yml up -d
   ```
2. เปิด http://localhost:9000 ล็อกอิน admin / admin แล้วตั้งรหัสผ่านใหม่
3. Create project → Manually → Project key `sai-mu-backend` → Set up → Locally → Generate token (เก็บ token ไว้เอง ห้ามส่งให้ใครหรือใส่ในโค้ด)
4. รันสแกน (ใส่ token ที่ช่อง <TOKEN>)
   ```powershell
   docker run --rm -e SONAR_HOST_URL=http://host.docker.internal:9000 -e SONAR_TOKEN=<TOKEN> -v "${PWD}:/usr/src" sonarsource/sonar-scanner-cli
   ```
5. รีเฟรชหน้า Overview ของโปรเจกต์ จะเห็น Bugs / Vulnerabilities / Security Hotspots / Code Smells / Duplications
6. ปิดเมื่อเสร็จ: `docker compose -f docker-compose.sonar.yml down` (ข้อมูลยังอยู่ใน volume)

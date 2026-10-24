"""แปลง .env เป็น env.yaml สำหรับ `gcloud run deploy --env-vars-file env.yaml`
รันบนเครื่องคุณเอง ไม่พิมพ์ค่าความลับออกหน้าจอ และ env.yaml ห้าม commit (อยู่ใน .gitignore แล้ว)
ใช้: python scripts/make_env_yaml.py --cors https://<project>.web.app"""
import argparse, json, pathlib

ap = argparse.ArgumentParser()
ap.add_argument("--cors", required=True, help="โดเมนเว็บแอป คั่นด้วย , ได้")
a = ap.parse_args()

root = pathlib.Path(__file__).resolve().parent.parent
env = {}
for line in (root / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    env[k.strip()] = v.strip().strip('"').strip("'")

env["ENVIRONMENT"] = "production"
env["CORS_ORIGINS"] = a.cors
env.pop("PORT", None)  # Cloud Run กำหนดเอง

out = root / "env.yaml"
out.write_text("".join(f"{k}: {json.dumps(v, ensure_ascii=False)}\n" for k, v in env.items()), encoding="utf-8")
print(f"เขียน {out.name} แล้ว {len(env)} ตัวแปร: {', '.join(env)}")

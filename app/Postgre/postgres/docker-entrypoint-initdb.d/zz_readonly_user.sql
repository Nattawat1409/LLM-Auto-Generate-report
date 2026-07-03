-- Read-only role สำหรับ Text2SQL (guardrail ระดับ DB) -> normal user ใช้
-- ชื่อไฟล์ขึ้นต้น zz_ เพื่อให้รันหลัง classicmodels_postgres.sql (ตารางต้องมีก่อนถึง GRANT ได้)

CREATE ROLE normal_user WITH LOGIN PASSWORD 'user';

GRANT CONNECT ON DATABASE classicmodels TO normal_user;
GRANT USAGE ON SCHEMA public TO normal_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO normal_user;

-- เผื่อมีตารางเพิ่มในอนาคต ให้อ่านได้อัตโนมัติ
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO normal_user;
e
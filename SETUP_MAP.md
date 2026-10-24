# ตั้งค่าแผนที่ (OpenStreetMap — ไม่ต้องมี API key / ไม่ต้องผูกบัตร)

## 1) ใส่ข้อมูลสถานที่ (backend)
```
python -m app.seed_sacred_places
```
เพิ่มสถานที่ 15 แห่งพร้อมพิกัด (รันซ้ำได้ ข้ามชื่อที่มีอยู่แล้ว) แล้วเปิด /admin/ เพื่อตรวจ/แก้
**พิกัดเป็นค่าประมาณ** ให้เทียบกับ Google Maps (คลิกขวาที่หมุด → คลิกตัวเลขพิกัดเพื่อคัดลอก) ก่อนส่งงาน

## 2) เพิ่มแพ็กเกจ
```
flutter pub add flutter_map latlong2 geolocator url_launcher
```
(โค้ดเขียนสำหรับ flutter_map รุ่น 7 ขึ้นไป และ geolocator 12 ขึ้นไป) แล้ว **หยุดแอปและรันใหม่ทั้งหมด**

## 3) แก้ applicationId ในโค้ด
ในไฟล์ `sacred_places_screen.dart` แก้ค่า `_appId` ให้ตรงกับ applicationId ของแอป
(ดูใน `android/app/build.gradle`) — OpenStreetMap ขอให้แอประบุตัวตนในการดึงแผนที่

## 4) Android — `android/app/src/main/AndroidManifest.xml`
```xml
<uses-permission android:name="android.permission.INTERNET"/>
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"/>
<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION"/>

<!-- ใต้ <manifest> เพื่อให้เปิดลิงก์นำทางใน Google Maps ได้ -->
<queries>
  <intent><action android:name="android.intent.action.VIEW"/><data android:scheme="https"/></intent>
</queries>
```

## 5) iOS (ถ้าใช้) — `ios/Runner/Info.plist`
```xml
<key>NSLocationWhenInUseUsageDescription</key>
<string>ใช้ตำแหน่งของคุณเพื่อแสดงสถานที่สิ่งศักดิ์สิทธิ์ใกล้เคียง</string>
```

## 6) ทดสอบ
- เครื่องจริง: อนุญาตตำแหน่ง → ชิป "ใกล้คุณที่สุด" และระยะทางขึ้นที่การ์ด
- Emulator: Extended controls → Location → ตั้งเป็นกรุงเทพฯ
- แผนที่ว่าง/เทา = ไม่มีอินเทอร์เน็ตหรือยังไม่ได้เพิ่มสิทธิ์ INTERNET (ถ้า build release)
- ถ้าไม่อนุญาตตำแหน่ง แผนที่ยังใช้ได้ แค่ไม่มีระยะทาง และมีแถบให้กดขออนุญาตใหม่

## หมายเหตุเรื่องการใช้งานจริง
เซิร์ฟเวอร์แผนที่ฟรีของ OpenStreetMap (tile.openstreetmap.org) มีนโยบายการใช้งานที่เหมาะกับโปรเจกต์ขนาดเล็ก/สาธิต
ถ้าเปิดให้ผู้ใช้จำนวนมาก ควรเปลี่ยนไปใช้ผู้ให้บริการแผนที่ที่มีแพ็กเกจรองรับ — แก้แค่ `urlTemplate` ใน `TileLayer`
ต้องแสดงข้อความ "© OpenStreetMap contributors" ไว้เสมอ (โค้ดใส่ไว้ที่มุมล่างซ้ายของแผนที่แล้ว)

## ชั้นรถไฟฟ้า
ปุ่ม "รถไฟฟ้า" บนแผนที่เปิด/ปิดชั้น OpenRailwayMap (ใช้เน็ตเพิ่ม ไม่ต้องมี key) — เป็นบริการฟรีสำหรับการใช้งานเบา ๆ และต้องแสดงเครดิต © OpenRailwayMap (โค้ดใส่ให้แล้ว)

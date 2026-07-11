# UI QA Report — miq.irobotsonline.com

วันที่ทดสอบ: 2026-07-11
ขอบเขต: Live dashboard, SSE state, control flow Stop → Start, chart range controls, signal filters, trade tools, data consistency

## Executive summary

พบทั้งหมด 8 รายการ: High 2, Medium 4, Low 2

## Findings

### UI-01 — Performance ใช้ฐานคงที่ $392 ทำให้เปอร์เซ็นต์ผิด (High / Data correctness)
- หน้าแสดงยอด Demo $3,957.16 แต่ NET PERFORMANCE = -7.65% และ chart header แสดงลด $30
- โค้ด `renderChartCurve()` ตั้ง `currentBalance = 392.00` และคำนวณเปอร์เซ็นต์เทียบ 392 แบบ hard-coded
- ผลคือ performance ไม่สัมพันธ์กับบัญชี Demo และจะผิดทันทีเมื่อยอดเริ่ม session เปลี่ยน
- ควรใช้ session starting balance จริงจาก API/DB

### UI-02 — Equity curve วาดทิศทางสวนกับผลขาดทุน (High / Visual + correctness)
- มี settled trade ขาดทุน -$30 แต่เส้นกราฟไต่ขึ้นจากซ้ายไปขวา
- สูตรพิกัด Y ทำให้ยอดลดจาก 392 เป็น 362 แต่จุดเปลี่ยนจาก y=240 เป็น y≈220 ซึ่งแสดงเป็นเส้นขึ้น
- ควรใช้ scale เดียวกันทั้งจุดเริ่มและจุดถัดไป และตรวจว่าขาดทุนต้องวาดลง

### UI-03 — ปุ่มช่วงเวลา Session/24H/7D/30D/All ยังไม่ทำงาน (Medium / Functional)
- คลิก 24H แล้ว active state ยังเป็น Session และ path กราฟไม่เปลี่ยน
- ไม่มี event listener หรือ API query สำหรับช่วงเวลา

### UI-04 — ตัวกรอง Signal Matrix ยังไม่ทำงาน (Medium / Functional)
- คลิก Near signal / Confirmed / Blocked แล้ว active state ยังเป็น All 15 และรายการไม่ถูกกรอง
- ปุ่มดูเหมือนใช้งานได้ แต่ไม่มี handler

### UI-05 — Search และ Export CSV ยังไม่ทำงาน (Medium / Functional)
- Search ไม่สร้าง input/modal และไม่เปลี่ยนตาราง
- Export CSV ไม่มี download/action
- ทั้งสองปุ่มไม่มี handler

### UI-06 — สถานะ Stopped ยังแสดง countdown และ Risk Engine = ARMED/READY (Medium / UX)
- หลัง Stop: BOT STATE เป็น STOPPED แต่ Next scan ยังนับถอยหลังต่อ
- Risk Engine ยังแสดง ARMED, SAFETY STOP READY และ NEXT $60 ซึ่งสื่อเหมือนพร้อมเปิดไม้
- ควร freeze countdown และเปลี่ยน risk status เป็น DISARMED/STOPPED

### UI-07 — สถิติ trades กำกวมเมื่อมี pending position (Low / Content)
- UI แสดง `0W / 1L · 2 trades` ขณะที่ Recent trades แสดงเพียง 1 แถว เพราะอีก 1 ไม้ pending
- ควรแสดง `1 settled · 1 open` หรือแยก total/open/settled ให้ชัด

### UI-08 — Mobile navigation ส่วน Overview/Scanner/Trades ยังไม่มี action (Low / Functional)
- ใน source มี mobile nav แต่ Overview/Scanner/Trades ไม่มี handler
- CONTROL ผูกกับ restart โดยตรง ไม่ใช่หน้า control/navigation

## สิ่งที่ทำงานผ่าน

- SSE เชื่อมต่อ ไม่มี JavaScript console error
- ค่า balance, MG L1, next amount $60 และ loss streak 1/5 ตรงกับ API
- Stop → confirmation → STOPPED → ปุ่ม Start ปรากฏ ทำงานผ่าน
- Start → confirmation → RUNNING ภายในไม่กี่วินาที ทำงานผ่าน
- Open position card แสดง CADCHF CALL L1 $60 และ pending settlement
- Recent settled trade แสดง CADCHF LOSS -$30

## หมายเหตุ

- ทดสอบบนบัญชี Demo ตาม state ปัจจุบัน
- ไม่ทดสอบ Restart เพื่อหลีกเลี่ยงการรบกวนไม้ที่เปิดอยู่
- ไม่ได้ Push GitHub และไม่ได้แก้ logic เทรด

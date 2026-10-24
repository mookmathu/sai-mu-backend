"""สมผุสดาวเคราะห์ (อังคาร พุธ พฤหัส ศุกร์ เสาร์ ราหู เกตุ มฤตยู) แบบสุริยยาตร์ไทย

แปลงจากสูตรในไฟล์ suriyatr1.xls (โมดูล SURIYA YATRA ชีท สุริยยาตรา คอลัมน์ S-Z)
ของ อ.สมเกียรติ ฟุ้งเกียรติ (Excel Expert Training / XLSiam) ตามพระคัมภีร์สุริยยาตรศิวาคม
ทุกบรรทัดอ้างอิงเซลล์ต้นฉบับ ตารางค่าคงที่ CODE = Q44:Z51 ถอดจากไฟล์โดยตรง
หน่วย: ลิปดา (21600 ลิปดา = 360 องศา = 12 ราศี)
"""
import math

from . import suriyayart as sy

_int = sy._int

# CODE (Q44:Z51): แถว A0,A1,A2,A3,B,C,D,E ของดาวรหัส 3,4,5,6,7,10  (อังคาร พุธ พฤหัส ศุกร์ เสาร์ มฤตยู)
CODE = {
    3: (1, 2, 16, 505, 5420, 127, 45, 0.266666666666667),
    4: (7, 46, 4, 1, 10642, 220, 100, 21),
    5: (1, 12, 1, 1032, 14297, 172, 92, 0.428571428571429),
    6: (5, 3, -10, 243, 10944, 80, 320, 11),
    7: (1, 30, 6, 10000, 11944, 247, 63, 1.16666666666667),
    10: (1, 84, 1, 7224, 16277, 124, 644, 0.428571428571429),
}
PLANET_ID = {"อังคาร": 3, "พุธ": 4, "พฤหัส": 5, "ศุกร์": 6, "เสาร์": 7, "ราหู": 8, "เกตุ": 9, "มฤตยู": 10}
_TBL = (0, 244, 427, 488, 488)  # CHOOSE(M+1, 0,244,427,488,488)
_INNER = (4, 6)                 # พุธ ศุกร์ ใช้ VV ในแถว 15 และ 27 (ไม่ใช่ Z)


def _sgn(x):
    return -1 if x < 0 else 1


def _wrap(x):
    """IF(x<0,x+21600,x) - INT(.../21600)*21600"""
    y = x + 21600 if x < 0 else x
    return y - _int(y / 21600) * 21600


def _interp(x, scale=1.0, plus_half=False, mult=1):
    m = _int(x)
    lo, hi = _TBL[m], _TBL[m + 1]
    v = (x - m) * (hi - lo) + lo
    return m, v


def _planet_sompus(pid, P, VV):
    A0, A1, A2, A3, B, C, D, E = CODE[pid]
    # แถว 13
    z13 = _int(P * A0 / A1) + _sgn(A2) * _int(abs(P * A2 / A3)) + B
    Z = z13 - _int(z13 / 21600) * 21600                                   # แถว 14
    base = VV if pid in _INNER else Z                                       # S15 / T15 (VV สำหรับพุธ ศุกร์)
    koti = base - C * 60 - 5400                                             # แถว 15
    J = math.sin(math.radians(koti / 60))                                   # 16
    rx = abs(math.degrees(math.asin(J))) / 30                               # 17
    m1, v = _interp(rx)                                                     # 18-19
    MK = _int(v + 0.5)
    MS = D * 60 - _sgn(J) * _int(MK / 2)                                    # 20
    bu = koti + 5400                                                        # 21
    I = math.sin(math.radians(bu / 60))                                     # 22
    rx1 = abs(math.degrees(math.asin(I))) / 30                              # 23
    m2, v = _interp(rx1)                                                    # 24
    MB = _int(v * 60)                                                       # 25
    R1 = _int(MB * 60 / MS)                                                 # 26
    MP = base - R1 * _sgn(I)                                                # 27
    other = Z if pid in _INNER else VV
    K1 = MP - other - 5400                                                  # 28
    Q = math.sin(math.radians(K1 / 60))                                     # 29
    rx2 = abs(math.degrees(math.asin(Q))) / 30                              # 30
    m3, v = _interp(rx2)                                                    # 31-32
    SK = _int(v + 0.5)
    puj1 = K1 + 5400                                                        # 33
    O = math.sin(math.radians(puj1 / 60))                                   # 34
    rx3 = abs(math.degrees(math.asin(O))) / 30                              # 35
    m4, v = _interp(rx3)                                                    # 36
    SB = _int(v * 60)                                                       # 37
    if pid in _INNER:                                                       # 38
        H = _int(_int(SB / 60 + 0.5) / 3) - SK * _sgn(Q) + E * 60
    else:
        H = _int(_int(SB / 60 + 0.5) / 3) - SK * _sgn(Q) + _int(MS * E)
    R2 = _int(SB * 60 / H)                                                  # 39
    return _wrap(MP - R2 * _sgn(O))                                         # 12


def planets_sompus(day, month, year, time_frac):
    """คืน dict ชื่อดาว -> สมผุส (ลิปดา 0-21600)"""
    _, VV = sy.sun_sompus(day, month, year, time_frac)
    js = sy.js_year(day, month, year, time_frac)                            # E14
    P = (js - 610) * 21600 + VV                                             # J28
    out = {}
    for name in ("อังคาร", "พุธ", "พฤหัส", "ศุกร์", "เสาร์", "มฤตยู"):
        out[name] = _planet_sompus(PLANET_ID[name], P, VV)
    x13 = _int(P / 20) + _int(P / 265)                                      # X13
    x14 = x13 - _int(x13 / 21600) * 21600                                   # X14
    out["ราหู"] = _wrap(15150 - x14)                                        # X12
    y13 = sy._horakun_jd(day, month, year) - 344                            # Y13 = E41-344
    y14 = _int(((y13 - _int(y13 / 679) * 679) + time_frac * 24 / 24) * 21600 / 679)
    y14 = y14 - _int(y14 / 21600) * 21600                                   # Y14
    out["เกตุ"] = _wrap(21600 - y14)                                        # Y12
    return out


def planets_rasi(day, month, year, time_frac):
    """คืน dict ชื่อดาว -> (ดัชนีราศี 0-11, องศา, ลิปดา)"""
    res = {}
    for n, s in planets_sompus(day, month, year, time_frac).items():
        r = _int(s / 1800)
        rem = s - r * 1800
        d = _int(rem / 60)
        res[n] = (r, d, rem - d * 60)
    return res

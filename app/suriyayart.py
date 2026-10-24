"""
Python port of the classical Thai Suriyayart (สุริยยาตร์) Sun & Moon
rasi (ราศี) calculation, transliterated from the Excel formulas found in
suriyatr1.xls (4ZSuriya, by อาจารย์สมเกียรติ ฟุ้งเกียรติ, Excel Expert Training,
based on พระคัมภีร์สุริยยาตรศิวาคม).

Every function below mirrors one Excel cell in the "สุริยยาตรา" sheet.
Cell references are kept as comments so this can be cross-checked against
the original spreadsheet cell-by-cell.
"""
import math

def _int(x):
    """Excel INT() = floor, not truncate."""
    return math.floor(x)

RASI_NAMES = [
    "เมษ", "พฤษภ", "เมถุน", "กรกฎ", "สิงห์", "กันย์",
    "ตุลย์", "พิจิก", "ธนู", "มังกร", "กุมภ์", "มีน",
]

# ---------------------------------------------------------------------
# Step 1: จุลศักราช (Chulasakarat / J.S.) year   -- cell E14
# ---------------------------------------------------------------------
def _talerng_sok_offset(js_year):
    """Fractional day-of-year at which Songkran (Thai New Year) falls,
    for a given J.S. year. Cells E26 / E44 / E45 use this same formula."""
    y = js_year
    return (y * 0.25875
            - _int(y / 4 + 0.5)
            + _int(y / 100 + 0.38)
            - _int(y / 400 + 0.595)
            - 5.53375)


def js_year(day, month, year, time_frac):
    """Cell E14."""
    y = year - 638
    threshold = _talerng_sok_offset(y)
    if month > 4 or (month == 4 and (day + time_frac) >= threshold):
        return year - 638
    return year - 639


# ---------------------------------------------------------------------
# Step 2: สุรทิน (Suratin) -- day count into the (April-starting) year
# cells E29 / J31:J47 / I34:I46 / H33:H46 / G34:G46
# ---------------------------------------------------------------------
def suratin(day, month, year, time_frac):
    js = js_year(day, month, year, time_frac)          # E14 / J31
    e26 = _talerng_sok_offset(js)                       # E26
    j32 = day + time_frac                                # J32

    months = [4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3, 4]  # G34:G46
    # H34:H46 -- the AD year associated with each month slot
    ad_years = [js + 638] * 9 + [js + 638 + 1] * 4        # H34:H42, H43:H46

    # I34:I46 -- month lengths (or partial-month value for the "current" month)
    i_vals = [None] * 13
    # I34 (April, special case)
    i_vals[0] = j32 if (month == 4 and j32 >= e26 and ad_years[0] == year) else 30
    fixed_lengths = {1: 31, 2: 30, 3: 31, 4: 31, 5: 30, 6: 31,
                      7: 30, 8: 31, 9: 31}  # positions 1..9 -> May..Jan (I35:I43)
    for idx in range(1, 10):
        i_vals[idx] = fixed_lengths[idx]
    # I44 (Feb) -- leap check on H44
    h44 = ad_years[10]
    i_vals[10] = 29 if h44 % 4 == 0 else 28
    i_vals[11] = 31   # I45 (Mar)
    i_vals[12] = 0    # I46 (blank cell in the original sheet)

    j_vals = [None] * 13
    j_vals[0] = i_vals[0] - e26   # J34
    for idx in range(1, 13):
        prev = j_vals[idx - 1]
        g = months[idx]
        h = ad_years[idx]
        if prev == 0:
            j_vals[idx] = 0
        elif g == month:
            j_vals[idx] = j32
        elif (g < month and h <= year) or (g > month and h < year):
            j_vals[idx] = i_vals[idx]
        else:
            j_vals[idx] = 0

    return sum(j_vals), js   # E29 (S), and J.S. year for reuse


# ---------------------------------------------------------------------
# Step 3: Sun -- Sompus Artit (equation-of-centre corrected longitude)
# cells H12:K28
# ---------------------------------------------------------------------
_SUN_EQC_TABLE = [0, 35, 67, 94, 116, 129, 134, 134]     # J26 CHOOSE table
_MOON_EQC_TABLE = [0, 77, 148, 209, 256, 286, 296, 296]  # N26 CHOOSE table


def _equation_of_centre(matyom_z, table):
    """Shared logic behind J21-J27 / N21-N26 (kan/khaen + R interpolation)."""
    puj = matyom_z - 4800                      # J22 (BU offset; N-side skips this term,
                                                 # handled by caller)
    i_sin = math.sin(math.radians(puj / 60))    # J23
    kan = abs(math.degrees(math.asin(i_sin))) / 15  # J24
    m = _int(kan)                                # J25
    frac = kan - m
    # CHOOSE is 1-indexed; table already 0-indexed to match CHOOSE(...+1,...)
    lo = table[m]
    hi = table[m + 1] if m + 1 < len(table) else table[-1]
    r = _int(frac * (hi - lo) + lo)              # J26
    return r, i_sin


def sun_sompus(day, month, year, time_frac):
    s, js = suratin(day, month, year, time_frac)     # E29 / J14
    kamuchapol = s * 800                              # J15
    rasi_seed = _int(kamuchapol / 24350)              # J16
    bal1 = kamuchapol - rasi_seed * 24350             # J17
    degree = _int(bal1 / 811)                          # J18
    bal2 = bal1 - degree * 811                          # J19
    libda = _int(bal2 / 14) - 3                         # J20
    matyom_z = rasi_seed * 1800 + degree * 60 + libda   # J21 (Matyom Artit)

    r, i_sin = _equation_of_centre(matyom_z, _SUN_EQC_TABLE)  # J22:J26
    sign = -1 if i_sin < 0 else 1
    raw = matyom_z - r * sign
    sompus = raw + 21600 if raw < 0 else raw
    sompus = sompus - _int(sompus / 21600) * 21600       # J12 -- Sompus Artit A

    vv = matyom_z - 23                                    # J27 -- Matyom Ravi VV
    return sompus, vv


def sun_rasi(day, month, year, time_frac):
    sompus, vv = sun_sompus(day, month, year, time_frac)
    rasi_idx = _int(sompus / 1800)     # J5
    remainder = sompus - rasi_idx * 1800
    degree = _int(remainder / 60)
    libda = remainder - degree * 60
    return rasi_idx, degree, libda


# ---------------------------------------------------------------------
# Step 4: Moon -- Sompus Jan
# cells L12:N26, uses "Horakun to needed day" (E41) instead of Suratin,
# and needs VV (Sun's J27) as an input.
# ---------------------------------------------------------------------
def _horakun_jd(day, month, year):
    """Cells E40 / E41 -- a Julian-day-like serial number."""
    e40 = (365 * year + day + _int(275 * month / 9)
           + 2 * _int(0.5 + 1 / month)
           + _int(year / 4) - _int(year / 100) + _int(year / 400) + 2)
    return e40 - 233142   # E41


def moon_sompus(day, month, year, time_frac, vv):
    n13 = _horakun_jd(day, month, year)                 # E41
    ujapol = (n13 - 621) - _int((n13 - 621) / 3232) * 3232   # N14
    inner = _int((ujapol + time_frac) * 21600 / 3232) + 2
    matyom_uj = inner - _int(inner / 21600) * 21600           # N15 (Matyom Uj MU)

    avaman_w = n13 * 703 + 650 + _int(time_frac * 24 * 703 / 24)  # N16
    masken = _int(avaman_w / 20760)                                # N17
    bal1 = avaman_w - masken * 20760                                # N18
    diti = _int(bal1 / 692)                                          # N19
    bal2 = bal1 - diti * 692                                          # N20

    matyom_z = diti * 720 + _int(1.04 * bal2) - 17 + vv     # N21 (Matyom Jan)
    ujvises = matyom_z - matyom_uj                            # N22

    i_sin = math.sin(math.radians(ujvises / 60))               # N23
    kan = abs(math.degrees(math.asin(i_sin))) / 15              # N24
    m = _int(kan)                                                 # N25
    frac = kan - m
    table = _MOON_EQC_TABLE
    lo = table[m]
    hi = table[m + 1] if m + 1 < len(table) else table[-1]
    r = _int(frac * (hi - lo) + lo)                               # N26

    sign = -1 if i_sin < 0 else 1
    raw = matyom_z - r * sign
    sompus = raw + 21600 if raw < 0 else raw
    sompus = sompus - _int(sompus / 21600) * 21600     # N12 -- Sompus Jan A
    return sompus


def moon_rasi(day, month, year, time_frac):
    _, vv = sun_sompus(day, month, year, time_frac)
    sompus = moon_sompus(day, month, year, time_frac, vv)
    rasi_idx = _int(sompus / 1800)
    remainder = sompus - rasi_idx * 1800
    degree = _int(remainder / 60)
    libda = remainder - degree * 60
    return rasi_idx, degree, libda


if __name__ == "__main__":
    # Validation against the sample values baked into suriyatr1.xls:
    # Day=16, Month=12, Year(A.D.)=2001, Time=11:11
    # Expected (from the spreadsheet's cached cells): Sun J5=8, Moon N5=8
    day, month, year = 16, 12, 2001
    time_frac = (11 + 11 / 60) / 24  # 11:11 as an Excel time fraction

    s_idx, s_deg, s_lib = sun_rasi(day, month, year, time_frac)
    m_idx, m_deg, m_lib = moon_rasi(day, month, year, time_frac)

    print(f"Sun : rasi={s_idx} ({RASI_NAMES[s_idx]}) {s_deg}°{s_lib}'")
    print(f"Moon: rasi={m_idx} ({RASI_NAMES[m_idx]}) {m_deg}°{m_lib}'")

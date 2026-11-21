#!/usr/bin/env python3
"""Generate publication-grade vector/300-DPI figures for the ArchaeoLiDAR-AR ResearchGate preprint.

Strictly respects Ley Nacional N° 25.743: NEVER reads confidential coordinate annexes
(`ANEXO_CONFIDENCIAL_COORDENADAS.json` or `CONFIDENTIAL_BLIND_KEY.json`). Uses only
generalized macro-zone centroids from `TARGET_ZONES`, public touristic coordinates from
`known_sites_published.csv`, and aggregated/non-coordinate metrics from the live corpus.
"""

from __future__ import annotations

import base64
import csv
import json
import re
import sys
import zlib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.gridspec as gridspec  # noqa: E402
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

PAPER_DIR = Path(__file__).resolve().parent
REPO_ROOT = PAPER_DIR.parents[1]
MCP_ROOT = REPO_ROOT / "archaeo-lidar-mcp"
FIG_DIR = PAPER_DIR / "figures"
PREVIEW_DIR = Path(
    "/Users/pablotempone/.gemini/antigravity/brain/7f681714-d877-4990-8f3c-42cbcba1da04/scratch/fig_previews"
)

sys.path.insert(0, str(MCP_ROOT))
from src.core.data_fetcher import TARGET_ZONES  # noqa: E402

# Embedded Natural Earth 50m outlines (clipped to Argentina + neighbors, lon [-76.5,-51.5], lat [-56.5,-20.0])
_SA_OUTLINES_B64 = (
    "eNp1XMvOdDlSfBU065mS7xd2gITEjg2rVi9+idHQojVIPQwSIN4dZ0ZGnjynqlaf4vPxLW2n8xKu//3dv/z21z/99cd//+5vf/rppz/0+mrl93+o9TXXz79XPPfB7VWB2ytPxWMaRvGuCvv5v2KrPl6lo1zhZO3WDa8bXq+mne9MCDyL4ToU52U4Se/ltafhLDi/drHmN/Bg/dQVNw5n5YPTa404nPTqLB9dcamGC74vi9MpinOz2a4KnA2nptilkbT7tCgs9N4NqnAyW29nGHG07VWKYhvtEcvQ2SdiwGYoV4WTuFfIbhJDtiabuPA///z73/3jj1///dcff/7Xv/mnv8ifv9j+WK8zxp5ftXKFKrCv0ALmirSsuLG8lwe2cq5oQXvd8Ub5IB6x/llh62+FFZX6Xj5ie1O388Gj8fumeHLHDbS3G/HZAb28ULxfRVEqBtNE6TRcm2IWA1VWZlv1jm07bF0R6Zutdch683ubu63o6R14bMMmym1DX5hqpeg2RF+4NL6SB//0hyHbOK7FZoXK9k12dljP9NBC4/zqrcMzXiuv9/Ywv9Of6AbB27DunSOfbnhsYJbrWnK/Hzwx/83v+77jYmvr/WFtoU3ke0A211fYCtfwsFWkPMpX8AzTvYkPAs1nJvqfxRaW9eAT6nHARzHUsPlu9blENqZ2nxE0xsHJhsQp5Hz/nLXlhP/zj99+BM2/dPzltMGTcQZTskMRfimXattNse2mcXaF4hQVv5QPU24L2A7D0X1Fsd0jXdVPqSYLUYZnMUvjUTsXTtXylakMG8q7Ybkqyqnm32fFtvmabpYyjhZk+02xX1yiyMp8JY5vZsWN881DsSm6gf7mq/PmEuV9sJ8u+9z1SlGca7ipTvfDcVacqadkc53hd948A9OrNS5H5/Q3xdV59paJb4etVSo3+9lTCtHdKKqKZLWqYdlYsvgz4mTNn+o7bJWwc2Rf/cO//fLrH7GpBsRwSrADF1YhcViOoc4PbugHYjm4o5yfFx0VCqcepzPoVQyrDAJOWSeZDIrxICJh27pDm6k39nU2Sjcs6khE7OUbO8rHakvWY/nZGJP1C3YYsZ6Aye83dwyMlYOH9L9sxx2sB3Dj6pkJK7htA57iDesBB04+h62R170c6unUz/2Oa4YxUgx3WBcY3ky0Pvo0XGA7ba9v1sfi+Iri5XipPcHhLpgXxYcLw7Cw+wRc2br03sNohuJCrNZKt3te8IHDroaZ9Wo82IozDMNhmliwmFrTjsNMGM1ZwmZ4A09+3xRuQrWdzooZnAWQxbKSLVG0WefeuDTyvcLKz0WVHoxrQfBZmXZa6fz8DKYVO+uzqK44uDhuimHjCD6w2tll9SN5705hZeti8RwMRcjB0uA/WGzeJvqVohuKOydfgE2URUUveBI3xZwcSjdbrzK4bopHJJsV9xwH3zk3x76Qci0cvDkb0QlNtHUQ9bhEqaIWOz3IYmKPnqHqYKbd8AfLkWiTW7qoMdoWB1v0jmmLu8yxLWTVI9u23SkH60Jt2+PH4h6ALBYD5GCba1X7JNmVIbWBbU8W2CNHV2aOvgFztGaZGzJDvPsuMONyBHUhxlWmdjPjleXFTFtqpwFTuPkJUji56Y6n0+lFyjIrdEHK8ROH5Ta4sCdlmQ72XbFQn2NXy7Zep3sCN98kj+oF5amGLXwGu7gn1ekoZlvIaGF4+pZWM6tyJY7kO/obXGfgwpWZ9V6/9dh+Ubexl2tX6kqWayUnsK1Vxfd+oisdh8VyW5uZ4/eF+7jCMC7mKMymF6PgRoz6hBg9LKlTewEX7sOxgtsivUOambNdwagVYc3LJ7rmVkc4Y512opyhEvahyA5G/fLmosMmc53BKZH6+Jwzt9YoqdlDcXvBIRn8euPIDM58t+Axnc/NubRbpmv44TpxDQ7LwcPwXIob6w+c0MryOlHOdckoXy55nPDN0atsEveN7YN0rfNGf6bdMD1XEE0vwdvnqN5ZLrpUFA6HU6G+Nrfdhr7aXl4UT5fmVsxTsaDtvPuE4laDtEU7FlZHcz0IRz4nbKpbR9jCbfHIN/VFBbNcdemC7Xf6qtDc2SWXVbNvimJC048RVl7KXZIV2FcSNwVhR3EnLqjuGyNbOSUnZq5cNGxe79RJA6Gpqm/j6k5stYOn10f59P5RbgqtQzqDV0XTjXGwrXTXQyTlBsX3afSFJnwfKebKieN+Xapd3Uy5hGccfr+GI/pHLu24b/qrBX0ikAud0HryU7EVFz+FuMN97fSK79QIVbW9YGoEG71ryw1hde67ZXgG7SgmBKvbZAhttK7tMPdKfbNvs6l6b4pBw9kCcmz1Zv4UjP0oCrcoFowrWiBjROPLem8WcBJcYLzxIpoKl19MCgdnnmDqVdfFA5Yi760FQ3PQdJsThiV1sRpbAVv5pbtRXsKtfmB1c0rNWp+7GprZgr1ir4xo9haol/yKir8x2iWCR3M9h0vw4LmCsmyM/nCbMHp2lbu1tWB199u2y9c1qJHtTf+n6uzqvow9UREH+7ZVf2pd4xNr72C/imRp6/R9ZrB6scK8w0ILnuGKPw6NS6PDX5rxGhX/iOUFmLJO6mzlGRwWiQX3YEBJrJjeT1fXbrhRjTD4oD01EDavNXhLjIqLOVXUc73MnaKOrnscot0OHvQ0N0IxNvaE4MRg8wmhmc6VTgg9Bd9QYyeN5g18yVIvT7YDlxF8S4kTuGdbEUdge3JxFQb+zJNm9COGOBCkWypNMa8YaNBrull7x3RWk6bZKT1YLh+JUNHTt8/z5aNIPIu2r6JG2SXDLZjhLYgKpTv4/JJYYPEaijN7XjPa6QkGS6VBguYqtVXSa+8y4y2AW3mrJhgUjbZcgu3WuDESbDe6miIIlFf6GAWS6BRUQrlHSPa+Dz/DDl87LFxn+uh8LxpGMx1hocXt8I2E6SZfaFi+u8X5FUaINuxDDzhtuDG0uy3C06lPbxsDW2UiQNsZ4p7w4c5WJtat0hnUWQjwdlMyEmNSAUClns9NYI6v5rVDXn7V8jO8bN1VavD2PYoD16AFe7pCZ1OnFf3atVTHBeAebcMF0VwHb1wgO16W5TJwr9FhvE1dLXGpZ7Tz9mUJddi0iaaK5gQCXvCpJ+c3YWQ2Gp1m0/YaTZvNs9/Rv/fXERLYdBE6zNLNI9BhqW2euM7x1ugytE2XokPem8ZNw622eMtoelWmz+Ff4oCAEEeX/7CDDkOYlp4ZvonjVVNtXeO/qlPi5qDNm5MRnM/coq/ekOWpdAdjfV/Dfe/TbHdzb/ur3G3rBWN59bDEqI4Gy8vcf3evoXauuw7RBHe3G7Reot0BrePe/IYSTDNYRT0aUaYEoxXlzVX25q5EzVFJYk/L6NxAtOCBO7AozvdYghtNPldfH/jXizv4ljWkE1os0CriRLDAd5zlhPwELXOCa3RatX3eZ9BByePekJdFjjRnL8UM8Q/TOSzW4Em323YgBy/5H36/oNIaw+gL3cGAFqWN5mbU4d1yABaWonnOK6Hb4kqYGYu1qEB9LtxLKd54WZ2R60pBHKvRtMjY/I3qMyMF2q5I04YCrnEntity651RHcOc9wBDitZ/ZbDTixEbrTU61P3FjTAQuB1+buA6xMrMdoh5u+FJeGSEI+HQ1OVt1zFoaG+0EPaRBjm3aa5LvjZua1ec5mqOmqsi3DDdC10xugGvVMIVixu3xHBFR1Qvvaj4rubYQYZu29Q7Hbq2UFcP6G4WN6jmtGKxB/07QwprhPFcV1PszgewoyajonNlvqHoZolu9rxU+VWda2LuoKuidVvy6mvANRtwL0cOTgbqu24eIYktujkkmCnjfF1vlpF25TKgTAqv26s5drAQ03IhI+ZU233Vbvd1J4MmVvcTA4NlrRhcqFxkxNBaDTE0lLtbeNXnCDOifh7NaCVGHBGsEYVZQzAH37OFipiAh1sGDqbHAe0Y7xjNoUpjcKlfgbKrOXSQYZi2y7Bt0FKbhq/p2EQPp61gNt7q0/CsUKuTlmKHWp3lgTMNU2jp7oaq15ec79//9uN/fvnVmAT5hUwhBNaRAapOHUCGSHhMKEc4v3IBvDrEEVvTsXeEyyVTaeUbtCmjABWSwCAs5dug+2lYSV2VpK2qUxPi04MoNcYX4tSTWHWnXd1JWU/S1pPU9SR9PThhD8bYO6HsTjh7EtLeCWsDOLN3pQks0rW67lzBHI1Evw4uHKw65ovcv1UjBwIBY+FMkFK2wJHIxBInOI48DoI6auq4O5cww5HvzuEowOsL5+POCXlyRt45JU/OCfgDtX+krLxTWu6Ulycl5sGYWWCMJDOEhHxYECgY1752DkXY1Hqe/uPXX/7rlx92oCYExYTyW1PvXT2pPF6dzKQdG3jjd7zzP578kAVRIARS0VwhtaJ5BIVYyThevWvgsBirbgw9I8WczAPrDHIdA/GeQqf3necxDa8PLJE3CsmTYfJkoDwZKn2FYE8UnKzT3/32pz/++T9/+fO1Uk/GqOH6hWD6JKBuhXuFhRPl8IW++kZvbVCVn+mw2CaiCUmuzKBsFHKYCnAfgdMk9FonX0JzJtY3ymgmyan3qDkXSByN2mZBk5p1LNWN/OvNL1CLnQPVNWaZyOWsCGHeuMSddMOJ2ZE6IJ+j+vTqSzGrF1BEXFUqX2XY4HDYBVI5iC1+wwjAGjlyIAbKlIuUV8Wbo1Oq8ryYzw3RX/aux3+S+WxzX7YNZSmW4ubcz6x4kCuqF8Ei1TCrlyeMFfK/jOCyecAlzlFpGw+7NJep0oOrtUeIzy2EqdyCq3VQDyqjGFa86cIV7Nttt4x0toDZegJuHFxG/eVstI3Qu0HQZThyTV4xqSp9b8XemGzag8e8xnagTxSNLba9kYQw3eNZAvNmK1IeZEmJplta3+QIb/tqvr1QbLS7pue/kcMxLNzkn3ckChNVGeztazgduTKSsgRjuMYxa/DqqFjNJeSNNhArcOaQYIvPcfQWz2vU2wgGNkPaGe+/0SDZ0Fqx9E8xWS2MxUVpxYsYjd8kXZAPEYiZuCBTDYHJYSnVwiC6JaMLJdPgzTFXNSxjWyzQN5DLbx6kb0j3eKy2sz9fORv9zvf+XPK6DZlEGHBcDrbIboew6rVy+Hx6MTw1mDbD4oiN+64z8Ve4MSyR2IiHeef8Hp97KZBDJCUTL9gMX92Uw2BGNPNC3pbTHAwzj0DKOngg4drpO1gCdxIjIQvdJfc5st/efQKkKBZy6z71iWR65Zmx6i7Jta9cvBgTFj6snNwEZnP7Vt6xESZJ14MRU+tuYiMsbpRJpsHmbAcizMWxsbpYf6J8UXgbUYjt1goi1s672vfiYQHvHnIIUs7wmXE+QjLK3emBG7qnKxi3jYHCcJkxWDqxccw8NVXhzycPt4GQwgQH+eaENXBxhj9Q6J74muExhoxmBv7NWORd1c8cNIs8FmZHNsJrxa5wJtYCvnHanpw3Ruty4PfN8KDijTP3ZNTZUxdPX+cgKpLGUkhvP+h5T/remndyT0L9OT7S/yzO7GSiN7ZgN/LOLRUT0tVPsuGTjPjgKmbkQfJnaiMob3IqPjIh35mSSGO0G/GSbugHomVF6zkH2V0pg3eiZm2Rj/NO7MxBo5CiOu8MWbJCM0yCebF5nxzSB8V0QhvW8oWROoDTNwbrk+H6ZMA+GbINytr5ucao9WT8k2H7YKDc6LlP9u6T3fvO/s0WZd5f2MJPNvGyey1/YR9beG5GJoLgO5e57xuXuX2hNhu/pewvTOiJzrNTlVHuNE2YDHvfeddzfeFdpx6zne88bTMpsnOVxx3PcRlvb7Tvd1r4ginqS2G2pbNa32jlsC3HvpgEYie3QOpo6VqpB0n9yWF/ctwHXADv/cmJf1DmG4p9aR4E+wR3xPn5dz4+iAuVbMAP9H24K42iSjVyb570f3seMC9Cizog86oP8o2XGhcnf3lckOAK+tTvjxGSLuTBTkOga8norrmWZX1625Dox8757SmE+cX1y9OJ59OKAi/dWR3xJcbzocbAy6LK/KZghe3TMw++CqlMYd1fhRhDozoz+/0RiUUoljM8FphINTBIqh+5BBIWHRiZawsRj/BopcW5l6v/5yOXBrzal0cxHeX12yOaiu9z+fLopiI8tON0Ep8kPd7wfH/j42+ANt4I+dZ4vhmKT4o+vDi6v0h6vlhafBOX44OnSXNr6WTkCV398gDKsMfpng+mNNTGEMuHB1Z48tY8MocncaV9e6+F91yL5XJxCi3s8/uv5/uwt+djb6/LEP0dPfgJpdDYHRZcbp+DmO9BzkcMNAO1TwFTuPlX5Wd89T3+WlB9fAzXPqK5oHEWN7MLh9oYzinoDZbrwMXi/LkBC6WQwjBgE5R6PR68v0VM/H6P8Gq1kDb2fMv49tYRb8p9oSXsCP7fvkXD2xVVvb+dfH9b+Xx7OZGWmDGaPji859NNhJ8HUyjvLz15Ckb4jQM5JeXLS9HHQ9L7O1NQvCTnwne4G+WthThloekrccr75/dnrLYtp92kb89eu17EguvHZ7Ide2cyKNtxCKlCPjyzvT/DRU68GDOdGSYa15LxMRWRv2SI7BXwKB8zSs+MExLoB+/xJUM1c1BJHYwMGZ7jqNLeMl6Nq1M8wwVxlM8Zs/eM2kb9SXEltD/np4QcokiiwCnspfo97c/ZPJ3Mup5oP5N/z+QgoO+sgtY84q00221Jp4FTZewKJs/2lfkoIAVPHsqGTEiqbz+94bTaG412gV3qCnjxxxf8rXALvDQpBtnzojEZZnCh45GVUy0bmFfOW8qghXlwIuXAQpOg2A5cH1HoLXBtB6TdydWQCB6oQ4PlGUyl4RG+HplLnVSjzVCwUY02L5QO3pVfX9m4oRQHKAOrvJGSIV9wC4WGzGCw1ZgezjVceYvMwFO2iGhnzNEeO7F/I2a260q6emNOcoFg7znGZEkFBu4TsgD+pH2DgJ+Z8rjq//zz//0/IJc6bA=="
)

# Macro-biome mapping for all 30 TARGET_ZONES (consistent with benchmark_v1._ZONE_BIOME_FALLBACK)
ZONE_BIOME_LABEL: Dict[str, str] = {
    "ZONA_1_TASTIL": "NOA Quebradas y Valles",
    "ZONA_2_YOCAVIL": "NOA Quebradas y Valles",
    "ZONA_3_TINOGASTA": "NOA Quebradas y Valles",
    "ZONA_4_TOLOMBON": "NOA Quebradas y Valles",
    "ZONA_5_LAPAYA": "NOA Quebradas y Valles",
    "ZONA_6_TILCARA": "NOA Quebradas y Valles",
    "ZONA_7_ACONQUIJA": "NOA Quebradas y Valles",
    "ZONA_8_SHINCAL": "NOA Quebradas y Valles",
    "ZONA_9_ALUMBRERA": "Puna y Alta Montaña",
    "ZONA_10_RINCONADA": "Puna y Alta Montaña",
    "ZONA_11_LACUEVA": "NOA Quebradas y Valles",
    "ZONA_12_USPALLATA": "Andes Cuyanos y Volcánico",
    "ZONA_13_SOMUNCURA": "Meseta Patagónica",
    "ZONA_14_LLULLAILLACO": "Puna y Alta Montaña",
    "ZONA_15_VOLCAN_GALAN": "Puna y Alta Montaña",
    "ZONA_16_LAGO_BUENOS_AIRES": "Meseta Patagónica",
    "ZONA_17_CHANI": "Puna y Alta Montaña",
    "ZONA_18_FAMATINA": "Puna y Alta Montaña",
    "ZONA_19_ACHALA": "Sierras Centrales",
    "ZONA_29_SIERRA_DE_MANCHAO": "Sierras Centrales",
    "ZONA_32_TAFI_DEL_VALLE": "Sierras Centrales",
    "ZONA_20_VALLE_GRANDE": "Yungas y Selva Montana",
    "ZONA_21_CIUDACITA": "Yungas y Selva Montana",
    "ZONA_22_TEYU_CUARE": "Selva Paranaense",
    "ZONA_23_DELTA_PARANA": "Humedales y Llanuras",
    "ZONA_24_IBERA": "Humedales y Llanuras",
    "ZONA_25_ANSENUZA": "Humedales y Llanuras",
    "ZONA_26_STROBEL": "Meseta Patagónica",
    "ZONA_27_PIEDRA_PARADA": "Meseta Patagónica",
    "ZONA_28_PAYUNIA": "Andes Cuyanos y Volcánico",
}

BIOME_PALETTE: Dict[str, str] = {
    "NOA Quebradas y Valles": "#E76F51",
    "Puna y Alta Montaña": "#1B365D",
    "Sierras Centrales": "#E9C46A",
    "Yungas y Selva Montana": "#2A9D8F",
    "Selva Paranaense": "#1D7874",
    "Humedales y Llanuras": "#457B9D",
    "Andes Cuyanos y Volcánico": "#8E5572",
    "Meseta Patagónica": "#6D597A",
}

SHORT_ZONE_NAMES: Dict[str, str] = {
    "ZONA_1_TASTIL": "Z1 Tastil",
    "ZONA_2_YOCAVIL": "Z2 Yocavil",
    "ZONA_3_TINOGASTA": "Z3 Tinogasta",
    "ZONA_4_TOLOMBON": "Z4 Tolombón",
    "ZONA_5_LAPAYA": "Z5 La Paya",
    "ZONA_6_TILCARA": "Z6 Tilcara",
    "ZONA_7_ACONQUIJA": "Z7 Aconquija",
    "ZONA_8_SHINCAL": "Z8 El Shincal",
    "ZONA_9_ALUMBRERA": "Z9 Alumbrera",
    "ZONA_10_RINCONADA": "Z10 Rinconada",
    "ZONA_11_LACUEVA": "Z11 La Cueva",
    "ZONA_12_USPALLATA": "Z12 Uspallata",
    "ZONA_13_SOMUNCURA": "Z13 Somuncurá",
    "ZONA_14_LLULLAILLACO": "Z14 Llullaillaco",
    "ZONA_15_VOLCAN_GALAN": "Z15 Volcán Galán",
    "ZONA_16_LAGO_BUENOS_AIRES": "Z16 Lago Bs. As.",
    "ZONA_17_CHANI": "Z17 Nev. Chañi",
    "ZONA_18_FAMATINA": "Z18 Famatina",
    "ZONA_19_ACHALA": "Z19 P. Achala",
    "ZONA_20_VALLE_GRANDE": "Z20 Valle Grande",
    "ZONA_21_CIUDACITA": "Z21 Ciudacita",
    "ZONA_22_TEYU_CUARE": "Z22 Teyú Cuaré",
    "ZONA_23_DELTA_PARANA": "Z23 Delta Paraná",
    "ZONA_24_IBERA": "Z24 Iberá",
    "ZONA_25_ANSENUZA": "Z25 Ansenuza",
    "ZONA_26_STROBEL": "Z26 Lago Strobel",
    "ZONA_27_PIEDRA_PARADA": "Z27 Piedra Parada",
    "ZONA_28_PAYUNIA": "Z28 La Payunia",
    "ZONA_29_SIERRA_DE_MANCHAO": "Z29 S. Manchao",
    "ZONA_32_TAFI_DEL_VALLE": "Z32 Tafí del Valle",
}


def setup_pub_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9.5,
            "axes.titlesize": 10.5,
            "axes.titleweight": "bold",
            "axes.labelsize": 9.5,
            "xtick.labelsize": 8.5,
            "ytick.labelsize": 8.5,
            "legend.fontsize": 8.2,
            "figure.dpi": 300,
            "savefig.dpi": 300,
            "axes.edgecolor": "#495057",
            "axes.linewidth": 0.8,
        }
    )


def load_outlines() -> Dict[str, List[List[List[float]]]]:
    raw = zlib.decompress(base64.b64decode(_SA_OUTLINES_B64))
    return json.loads(raw.decode("utf-8"))


def save_dual(fig: plt.Figure, stem: str) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = FIG_DIR / f"{stem}.pdf"
    png_path = PREVIEW_DIR / f"{stem}.png"
    fig.savefig(pdf_path, bbox_inches="tight", pad_inches=0.08)
    fig.savefig(png_path, bbox_inches="tight", pad_inches=0.08, dpi=200)
    plt.close(fig)
    print(f"Saved: {pdf_path} (+ preview {png_path})")


def make_fig2_national_coverage_map() -> None:
    outlines = load_outlines()
    known_sites: List[Dict[str, Any]] = []
    csv_path = MCP_ROOT / "data" / "known_sites_published.csv"
    with csv_path.open("r", encoding="utf-8") as fp:
        for row in csv.DictReader(fp):
            known_sites.append(
                {
                    "name": row["name"],
                    "lon": float(row["lon_wgs84"]),
                    "lat": float(row["lat_wgs84"]),
                }
            )

    fig = plt.figure(figsize=(12.4, 8.5))
    gs = gridspec.GridSpec(2, 2, width_ratios=[1.48, 1.05], height_ratios=[1.14, 0.86], wspace=0.14, hspace=0.18)
    ax_main = fig.add_subplot(gs[:, 0])
    ax_noa = fig.add_subplot(gs[0, 1])
    ax_leg = fig.add_subplot(gs[1, 1])

    # POSGAR 2007 belts
    belt_bounds = [-75.5, -70.5, -67.5, -64.5, -61.5, -58.5, -55.5, -52.5]
    belt_epsg = [5343, 5344, 5345, 5346, 5347, 5348, 5349]

    def draw_basemap(ax: plt.Axes, is_inset: bool = False) -> None:
        ax.set_facecolor("#EAF2F8")
        for i in range(len(belt_bounds) - 1):
            x0, x1 = belt_bounds[i], belt_bounds[i + 1]
            if i % 2 == 1:
                ax.axvspan(x0, x1, color="#DCE7F2", alpha=0.35, zorder=0)
        for name, rings in outlines.items():
            is_arg = name in ("Argentina", "Falkland Islands")
            fc = "#FBFBFD" if is_arg else "#ECEFF2"
            ec = "#1B365D" if is_arg else "#ADB5BD"
            lw = 0.95 if is_arg else 0.55
            zo = 2 if is_arg else 1
            for ring in rings:
                xs = [pt[0] for pt in ring]
                ys = [pt[1] for pt in ring]
                ax.fill(xs, ys, facecolor=fc, edgecolor=ec, linewidth=lw, zorder=zo)
        for xb in belt_bounds[1:-1]:
            ax.axvline(xb, color="#5C6B73", linestyle="--", linewidth=0.75 if not is_inset else 0.95, alpha=0.7, zorder=3)

    draw_basemap(ax_main, is_inset=False)
    ax_main.set_xlim(-75.2, -52.5)
    ax_main.set_ylim(-56.2, -19.4)
    ax_main.set_aspect(1.18)

    # Top banner labels for POSGAR 2007 belts
    for i, epsg in enumerate(belt_epsg):
        xc = 0.5 * (belt_bounds[i] + belt_bounds[i + 1])
        ax_main.text(
            xc,
            -20.0,
            f"F{i+1}\n({epsg})",
            ha="center",
            va="top",
            fontsize=7.2,
            fontweight="bold",
            color="#1B365D",
            bbox=dict(boxstyle="round,pad=0.18", facecolor="white", edgecolor="#CBD5E1", alpha=0.92),
            zorder=8,
        )

    # Plot 30 TARGET_ZONES
    biome_counts: Counter[str] = Counter()
    zone_coords: Dict[str, Tuple[float, float, str]] = {}
    for zk, zinfo in TARGET_ZONES.items():
        b = zinfo["bbox_wgs84"]
        lon_c = 0.5 * (b[0] + b[2])
        lat_c = 0.5 * (b[1] + b[3])
        blabel = ZONE_BIOME_LABEL[zk]
        biome_counts[blabel] += 1
        zone_coords[zk] = (lon_c, lat_c, blabel)
        col = BIOME_PALETTE[blabel]
        ax_main.scatter(lon_c, lat_c, s=54, color=col, edgecolor="white", linewidth=0.75, zorder=6)

    # Plot San Rafael UAV Zenodo:3383227
    ax_main.scatter(-68.30, -34.60, marker="*", s=165, color="#F4A261", edgecolor="#1B365D", linewidth=0.85, zorder=7)

    # Plot 9 public touristic sites
    for ks in known_sites:
        ax_main.scatter(
            ks["lon"],
            ks["lat"],
            marker="^",
            s=42,
            facecolor="white",
            edgecolor="#1B365D",
            linewidth=1.1,
            zorder=7,
        )

    # Main map non-overlapping labels (only zones outside NOA inset + key anchors)
    main_label_offsets: Dict[str, Tuple[float, float, str]] = {
        "ZONA_12_USPALLATA": (-0.45, 0.75, "right"),
        "ZONA_19_ACHALA": (0.60, -0.30, "left"),
        "ZONA_25_ANSENUZA": (0.60, 0.30, "left"),
        "ZONA_24_IBERA": (0.65, -0.55, "left"),
        "ZONA_22_TEYU_CUARE": (-0.65, 0.65, "right"),
        "ZONA_23_DELTA_PARANA": (-0.55, -0.60, "right"),
        "ZONA_28_PAYUNIA": (0.60, -0.45, "left"),
        "ZONA_13_SOMUNCURA": (0.65, 0.25, "left"),
        "ZONA_27_PIEDRA_PARADA": (0.65, -0.35, "left"),
        "ZONA_16_LAGO_BUENOS_AIRES": (0.65, 0.45, "left"),
        "ZONA_26_STROBEL": (0.65, -0.45, "left"),
    }
    for zk, (dx, dy, ha) in main_label_offsets.items():
        lon_c, lat_c, _ = zone_coords[zk]
        ax_main.annotate(
            SHORT_ZONE_NAMES[zk],
            xy=(lon_c, lat_c),
            xytext=(lon_c + dx, lat_c + dy),
            fontsize=7.3,
            color="#1E293B",
            ha=ha,
            va="center",
            arrowprops=dict(arrowstyle="-", color="#64748B", lw=0.6),
            zorder=8,
        )
    ax_main.annotate(
        "UAV San Rafael\n(ZENODO:3383227)",
        xy=(-68.30, -34.60),
        xytext=(-66.7, -34.7),
        fontsize=7.4,
        fontweight="bold",
        color="#9A3412",
        ha="left",
        va="center",
        arrowprops=dict(arrowstyle="-", color="#9A3412", lw=0.7),
        zorder=8,
    )
    ax_main.text(-59.5, -50.6, "Islas Malvinas", fontsize=7.5, style="italic", color="#475569", ha="center", zorder=8)
    ax_main.text(-58.2, -43.5, "Océano\nAtlántico Sur", fontsize=8.2, style="italic", color="#5B7C99", ha="center", zorder=8)
    ax_main.text(-72.8, -36.5, "Chile", fontsize=8.0, color="#64748B", ha="center", rotation=78, zorder=4)

    # NOA zoom bounding box on main map
    noa_lon0, noa_lon1 = -69.9, -63.1
    noa_lat0, noa_lat1 = -29.8, -21.5
    rect = mpatches.Rectangle(
        (noa_lon0, noa_lat0),
        noa_lon1 - noa_lon0,
        noa_lat1 - noa_lat0,
        fill=False,
        edgecolor="#C1121F",
        linewidth=1.15,
        linestyle="-",
        zorder=8,
    )
    ax_main.add_patch(rect)
    ax_main.text(noa_lon1 + 0.25, noa_lat0 + 0.1, "Región B\n(detalle)", fontsize=7.3, fontweight="bold", color="#C1121F", va="bottom")

    # Scale bar (~500 km at 40°S)
    sb_lon0, sb_lat = -60.5, -54.5
    sb_deg = 500.0 / (111.32 * np.cos(np.radians(40.0)))
    ax_main.plot([sb_lon0, sb_lon0 + sb_deg], [sb_lat, sb_lat], color="#1B365D", lw=2.2, zorder=9)
    ax_main.plot([sb_lon0, sb_lon0], [sb_lat - 0.25, sb_lat + 0.25], color="#1B365D", lw=1.4, zorder=9)
    ax_main.plot([sb_lon0 + sb_deg, sb_lon0 + sb_deg], [sb_lat - 0.25, sb_lat + 0.25], color="#1B365D", lw=1.4, zorder=9)
    ax_main.text(sb_lon0 + 0.5 * sb_deg, sb_lat + 0.45, "500 km (ref. 40°S)", fontsize=7.5, ha="center", color="#1B365D", zorder=9)

    ax_main.set_xlabel("Longitud WGS84 (°)")
    ax_main.set_ylabel("Latitud WGS84 (°)")
    ax_main.set_title("A. Cobertura Nacional, Fajas POSGAR 2007 y Campaña (30 Zonas + UAV)")

    # Top-right: Zoomed NOA/Sierras inset
    draw_basemap(ax_noa, is_inset=True)
    ax_noa.set_xlim(noa_lon0, noa_lon1)
    ax_noa.set_ylim(noa_lat0, noa_lat1)
    ax_noa.set_aspect(1.08)
    ax_noa.text(-68.7, -21.75, "Faja 2 (5344)", fontsize=7.1, fontweight="bold", color="#1B365D", bbox=dict(boxstyle="round,pad=0.14", fc="white", ec="#CBD5E1"))
    ax_noa.text(-65.5, -21.75, "Faja 3 (5345)", fontsize=7.1, fontweight="bold", color="#1B365D", bbox=dict(boxstyle="round,pad=0.14", fc="white", ec="#CBD5E1"))

    # Fine-tuned offsets for 0 label collisions in NOA inset
    custom_noa_offsets = {
        "ZONA_10_RINCONADA": (-0.28, -0.25, "right"),
        "ZONA_11_LACUEVA": (0.25, 0.28, "left"),
        "ZONA_20_VALLE_GRANDE": (-0.25, 0.14, "right"),
        "ZONA_6_TILCARA": (0.28, -0.28, "left"),
        "ZONA_17_CHANI": (-0.28, 0.18, "right"),
        "ZONA_1_TASTIL": (0.28, 0.12, "left"),
        "ZONA_14_LLULLAILLACO": (0.26, 0.08, "left"),
        "ZONA_5_LAPAYA": (0.28, 0.05, "left"),
        "ZONA_9_ALUMBRERA": (-0.22, 0.35, "right"),
        "ZONA_15_VOLCAN_GALAN": (0.18, 0.38, "left"),
        "ZONA_4_TOLOMBON": (0.28, 0.22, "left"),
        "ZONA_2_YOCAVIL": (0.28, -0.04, "left"),
        "ZONA_32_TAFI_DEL_VALLE": (0.26, -0.32, "left"),
        "ZONA_21_CIUDACITA": (-0.32, 0.25, "right"),
        "ZONA_7_ACONQUIJA": (-0.36, -0.10, "right"),
        "ZONA_8_SHINCAL": (-0.24, -0.45, "right"),
        "ZONA_3_TINOGASTA": (-0.24, 0.35, "right"),
        "ZONA_29_SIERRA_DE_MANCHAO": (0.28, -0.10, "left"),
        "ZONA_18_FAMATINA": (0.28, -0.10, "left"),
    }
    for zk, (lo, la, bl) in zone_coords.items():
        if noa_lon0 <= lo <= noa_lon1 and noa_lat0 <= la <= noa_lat1:
            ax_noa.scatter(lo, la, s=58, color=BIOME_PALETTE[bl], edgecolor="white", linewidth=0.8, zorder=6)
            dx, dy, ha = custom_noa_offsets.get(zk, (0.25, 0.15, "left"))
            ax_noa.annotate(
                SHORT_ZONE_NAMES[zk],
                xy=(lo, la),
                xytext=(lo + dx, la + dy),
                fontsize=6.7,
                color="#1E293B",
                ha=ha,
                va="center",
                arrowprops=dict(arrowstyle="-", color="#64748B", lw=0.55),
                zorder=8,
            )
    for ks in known_sites:
        if noa_lon0 <= ks["lon"] <= noa_lon1 and noa_lat0 <= ks["lat"] <= noa_lat1:
            ax_noa.scatter(ks["lon"], ks["lat"], marker="^", s=44, facecolor="white", edgecolor="#1B365D", lw=1.1, zorder=7)

    for sp in ax_noa.spines.values():
        sp.set_edgecolor("#C1121F")
        sp.set_linewidth(1.1)
    ax_noa.set_xlabel("Longitud WGS84 (°)", fontsize=8.5)
    ax_noa.set_ylabel("Latitud WGS84 (°)", fontsize=8.5)
    ax_noa.set_title("B. Detalle NOA y Sierras Centrales (19 zonas)")

    # Bottom-right: Structured legend panel
    ax_leg.axis("off")
    handles: List[Any] = []
    for blabel in [
        "NOA Quebradas y Valles",
        "Puna y Alta Montaña",
        "Sierras Centrales",
        "Yungas y Selva Montana",
        "Selva Paranaense",
        "Humedales y Llanuras",
        "Andes Cuyanos y Volcánico",
        "Meseta Patagónica",
    ]:
        cnt = biome_counts[blabel]
        z_word = "zona" if cnt == 1 else "zonas"
        handles.append(
            plt.Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor=BIOME_PALETTE[blabel],
                markeredgecolor="#334155",
                markersize=7.2,
                label=f"{blabel} ({cnt} {z_word})",
            )
        )
    handles.append(
        plt.Line2D(
            [0],
            [0],
            marker="*",
            color="w",
            markerfacecolor="#F4A261",
            markeredgecolor="#1B365D",
            markersize=10.0,
            label="UAV Fotogramétrico San Rafael (ZENODO:3383227)",
        )
    )
    handles.append(
        plt.Line2D(
            [0],
            [0],
            marker="^",
            color="w",
            markerfacecolor="white",
            markeredgecolor="#1B365D",
            markeredgewidth=1.1,
            markersize=7.0,
            label=f"Sitios turísticos publicados ±100 m (N={len(known_sites)})",
        )
    )
    leg = ax_leg.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.03),
        frameon=True,
        facecolor="#F8FAFC",
        edgecolor="#CBD5E1",
        title="Biomas Calibrados y Fuentes de Referencia",
        title_fontsize=8.8,
        fontsize=7.8,
        labelspacing=0.45,
        borderpad=0.65,
    )
    leg.get_title().set_fontweight("bold")
    ax_leg.text(
        0.5,
        -0.05,
        "Nota Ley N° 25.743: Se muestran únicamente centroides regionales\n"
        "generalizados de las 30 zonas y sitios públicos turísticos (±100 m).\n"
        "Ninguna coordenada puntual de anomalía inédita es divulgada.",
        ha="center",
        va="bottom",
        fontsize=7.3,
        color="#475569",
        style="italic",
        transform=ax_leg.transAxes,
    )

    save_dual(fig, "fig2_national_coverage_map")


def _parse_ml_metrics() -> Tuple[List[Tuple[str, float]], Dict[str, Tuple[float, float, float]]]:
    txt = (MCP_ROOT / "data" / "reports" / "ML_BENCHMARK_METRICS.md").read_text(encoding="utf-8")
    feat_rows: List[Tuple[str, float]] = []
    for m in re.finditer(r"\|\s*`([^`]+)`\s*\|\s*([0-9.]+)\s*\|", txt):
        feat_rows.append((m.group(1), float(m.group(2))))
    clean = txt.replace("**", "")
    class_metrics: Dict[str, Tuple[float, float, float]] = {}
    for label, pat in [
        ("Clase 0 (Neg.)", r"\|\s*0\s+—[^|]+\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|"),
        ("Clase 1 (Pos. sint.)", r"\|\s*1\s+—[^|]+\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|"),
        ("Macro-prom.", r"\|\s*Macro-promedio\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|"),
    ]:
        m = re.search(pat, clean)
        if m:
            class_metrics[label] = (float(m.group(1)), float(m.group(2)), float(m.group(3)))
    return feat_rows, class_metrics


def make_fig3_scale_and_ml() -> None:
    desc_raw = json.loads((MCP_ROOT / "data" / "reports" / "DESCARTES_VLM.json").read_text(encoding="utf-8"))["discarded"]
    feat_rows, class_metrics = _parse_ml_metrics()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.6, 5.1), gridspec_kw={"width_ratios": [1.08, 1.0], "wspace": 0.30})

    # Panel A: Physical detectability floor A_min = 2 * GSD^2
    gsd = np.logspace(np.log10(0.03), np.log10(45.0), 300)
    amin = 2.0 * (gsd ** 2)

    ax1.set_xscale("log")
    ax1.set_yscale("log")
    ax1.set_xlim(0.03, 45.0)
    ax1.set_ylim(0.0025, 350000.0)

    # Archaeological target area bands
    bands = [
        (6.0, 50.0, "Parapetos / Chenques patagónicos (6–50 m²)", "#E9C46A", 0.16, 0.036, 9.5),
        (12.0, 80.0, "Casas-pozo Comechingones (12–80 m²)", "#F4A261", 0.15, 0.036, 54.0),
        (100.0, 1500.0, "Recintos / Kanchas andinas (100–1500 m²)", "#457B9D", 0.12, 0.036, 420.0),
        (1800.0, 9000.0, "Cerritos / Pucarás mayores (1800–9000 m²)", "#2A9D8F", 0.14, 0.036, 4100.0),
    ]
    for y0, y1, lbl, col, al, tx, ty in bands:
        ax1.axhspan(y0, y1, color=col, alpha=al, zorder=1)
        ax1.text(tx, ty, lbl, fontsize=6.9, color="#1E293B", va="center", zorder=4)

    ax1.fill_between(gsd, 0.0025, amin, color="#FADBD8", alpha=0.55, zorder=2, label=r"Zona irrecuperable ($A < 2\,\mathrm{GSD}^2$)")
    ax1.plot(gsd, amin, color="#1B365D", lw=2.3, zorder=5, label=r"Piso físico: $A_{\min,\mathrm{eff}} = 2 \cdot \mathrm{GSD}_{\mathrm{nativo}}^2$")

    # Sensor tier vertical markers
    tiers = [
        (0.05, 0.005, "UAV 5 cm\n(0.005 m²)", (0.10, 0.0042)),
        (0.50, 0.50, "LiDAR/UAV 0.5 m\n(0.5 m²)", (0.58, 0.16)),
        (5.0, 50.0, "IGN 5 m\n(50 m²)", (5.8, 13.0)),
        (30.0, 1800.0, "GLO-30 / FABDEM\n30 m (1800 m²)", (14.5, 16000.0)),
    ]
    for gx, ay, tlbl, (tx, ty) in tiers:
        ax1.axvline(gx, color="#64748B", ls=":", lw=0.9, zorder=3)
        ax1.scatter([gx], [ay], color="#1B365D", s=34, zorder=6)
        ax1.annotate(
            tlbl,
            xy=(gx, ay),
            xytext=(tx, ty),
            fontsize=7.3,
            fontweight="bold",
            color="#1B365D",
            arrowprops=dict(arrowstyle="->", color="#475569", lw=0.75),
            zorder=7,
        )

    # Overlay empirical discarded points
    rng = np.random.default_rng(42)
    nat_x, nat_y, art_x, art_y = [], [], [], []
    for cid, entry in desc_raw.items():
        area = float(entry.get("area_m2") or 0.0)
        if area <= 0:
            continue
        gx = 0.05 if cid.startswith("ARQ-HRM-") else 30.0 * rng.uniform(0.90, 1.11)
        if entry.get("vlm_verdict", {}).get("verdict") == "ARTEFACTO":
            art_x.append(gx)
            art_y.append(area)
        else:
            nat_x.append(gx)
            nat_y.append(area)

    ax1.scatter(nat_x, nat_y, s=16, alpha=0.68, color="#2A9D8F", edgecolor="none", zorder=6, label="Descartes NATURAL (N=98)")
    ax1.scatter(art_x, art_y, s=22, alpha=0.80, marker="s", color="#E76F51", edgecolor="white", lw=0.3, zorder=6, label="Descartes ARTEFACTO (N=23)")

    ax1.set_xlabel(r"Resolución nativa del sensor, $\mathrm{GSD}_{\mathrm{nativo}}$ [m/px]")
    ax1.set_ylabel(r"Superficie de anomalía / estructura [m²]")
    ax1.set_title("A. Ley Física de Detectabilidad Multi-Resolución")
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    ax1.legend(loc="upper left", fontsize=7.3, frameon=True, facecolor="white", framealpha=0.92, edgecolor="#CBD5E1")

    # Panel B: ML feature importances + OOF inset
    feat_names = [f[0] for f in reversed(feat_rows)]
    feat_vals = [f[1] for f in reversed(feat_rows)]
    pretty_names = {
        "rectangularity": "rectangularity",
        "slrm_std_window": "slrm_std_window",
        "area_m2": "area_m2",
        "aspect_ratio": "aspect_ratio",
        "slope_mean_deg": "slope_mean_deg",
        "dz_extreme_window": "dz_extreme_window",
        "dz_abs": "dz_abs",
        "dz_contrast_ratio": "dz_contrast_ratio",
        "circularity": "circularity",
        "dz_mean": "dz_mean",
    }
    ylabels = [pretty_names.get(n, n) for n in feat_names]
    bar_colors = []
    for n in feat_names:
        if n in ("rectangularity", "area_m2", "aspect_ratio", "circularity"):
            bar_colors.append("#1B365D")
        elif n in ("slrm_std_window", "slope_mean_deg", "dz_extreme_window", "dz_contrast_ratio"):
            bar_colors.append("#2A9D8F")
        else:
            bar_colors.append("#457B9D")

    y_pos = np.arange(len(feat_names))
    bars = ax2.barh(y_pos, feat_vals, color=bar_colors, height=0.65, edgecolor="none", zorder=3)
    for b, val in zip(bars, feat_vals):
        ax2.text(val + 0.006, b.get_y() + b.get_height() / 2.0, f"{val:.4f}", va="center", fontsize=7.6, color="#1E293B")

    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(ylabels, fontsize=8.0)
    ax2.set_xlim(0, 0.49)
    ax2.set_xlabel("Importancia media en folds (GradientBoosting)")
    ax2.set_title("B. Calibrador ML: Importancia de Rasgos y Métricas OOF")
    ax2.grid(axis="x", linestyle="--", alpha=0.4, zorder=0)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)

    fam_handles = [
        mpatches.Patch(color="#1B365D", label="Morfometría geométrica"),
        mpatches.Patch(color="#2A9D8F", label="Contexto SLRM / Pendiente (r=75 m)"),
        mpatches.Patch(color="#457B9D", label="Amplitud vertical (dZ)"),
    ]
    ax2.legend(
        handles=fam_handles,
        loc="upper right",
        bbox_to_anchor=(0.99, 0.82),
        fontsize=7.0,
        frameon=True,
        facecolor="white",
        edgecolor="#CBD5E1",
    )

    # Inset for OOF StratifiedGroupKFold metrics
    ax_ins = ax2.inset_axes([0.43, 0.08, 0.54, 0.42])
    groups_lbl = ["Clase 0\n(Neg. real)", "Clase 1\n(Pos. sint.)", "Macro-\nprom."]
    x = np.arange(len(groups_lbl))
    w = 0.24
    prec = [class_metrics["Clase 0 (Neg.)"][0], class_metrics["Clase 1 (Pos. sint.)"][0], class_metrics["Macro-prom."][0]]
    rec = [class_metrics["Clase 0 (Neg.)"][1], class_metrics["Clase 1 (Pos. sint.)"][1], class_metrics["Macro-prom."][1]]
    f1 = [class_metrics["Clase 0 (Neg.)"][2], class_metrics["Clase 1 (Pos. sint.)"][2], class_metrics["Macro-prom."][2]]
    ax_ins.bar(x - w, prec, width=w, color="#1B365D", label="Prec.")
    ax_ins.bar(x, rec, width=w, color="#2A9D8F", label="Rec.")
    ax_ins.bar(x + w, f1, width=w, color="#E76F51", label="F1")
    for xi, (p, r, f) in enumerate(zip(prec, rec, f1)):
        ax_ins.text(xi - w, p + 0.02, f"{p:.2f}", ha="center", fontsize=6.2)
        ax_ins.text(xi, r + 0.02, f"{r:.2f}", ha="center", fontsize=6.2)
        ax_ins.text(xi + w, f + 0.02, f"{f:.2f}", ha="center", fontsize=6.2)
    ax_ins.set_ylim(0, 1.18)
    ax_ins.set_xticks(x)
    ax_ins.set_xticklabels(groups_lbl, fontsize=6.8)
    ax_ins.tick_params(axis="y", labelsize=6.8)
    ax_ins.set_title("OOF StratifiedGroupKFold (5 folds, modo advisory)", fontsize=7.2, fontweight="bold", pad=3)
    ax_ins.legend(loc="lower left", ncol=3, fontsize=6.2, frameon=True, facecolor="white", edgecolor="#CBD5E1")
    ax_ins.spines["top"].set_visible(False)
    ax_ins.spines["right"].set_visible(False)
    ax_ins.patch.set_facecolor("#F8FAFC")
    ax_ins.patch.set_alpha(0.95)

    save_dual(fig, "fig3_scale_detectability_physics")


def make_fig4_campaign_results() -> None:
    desc_raw = json.loads((MCP_ROOT / "data" / "reports" / "DESCARTES_VLM.json").read_text(encoding="utf-8"))["discarded"]
    inv_raw = json.loads((MCP_ROOT / "data" / "reports" / "INVENTARIO_GEOMORFOLOGICO.geojson").read_text(encoding="utf-8"))["features"]

    # Panel A counts
    by_type: Dict[str, Counter[str]] = defaultdict(Counter)
    cert_nat, dz_nat = [], []
    cert_art, dz_art = [], []
    pos_cnt, neg_cnt = 0, 0
    for cid, entry in desc_raw.items():
        atype = entry.get("anomaly_type", "desconocido")
        vv = entry.get("vlm_verdict", {})
        verd = vv.get("verdict", "NATURAL")
        by_type[atype][verd] += 1
        dz = float(entry.get("mean_elevation_m", 0.0))
        if dz < 0:
            neg_cnt += 1
        else:
            pos_cnt += 1
        c = float(vv.get("certainty_pct", 0.0))
        if verd == "ARTEFACTO":
            cert_art.append(c)
            dz_art.append(abs(dz))
        else:
            cert_nat.append(c)
            dz_nat.append(abs(dz))

    order_types = sorted(by_type.keys(), key=lambda k: sum(by_type[k].values()))
    nat_vals = [by_type[k]["NATURAL"] for k in order_types]
    art_vals = [by_type[k]["ARTEFACTO"] for k in order_types]
    pretty_types = {
        "terraza_lineal": "Terraza lineal (+)",
        "estructura_circular": "Estructura circular (+)",
        "recinto_ortogonal": "Recinto ortogonal (+)",
        "estructura_hundida": "Estructura hundida (-)",
        "zanja_lineal": "Zanja lineal (-)",
    }

    # Panel B counts
    sub_counts = Counter(f["properties"].get("geomorph_subtype", "geoforma_no_clasificada") for f in inv_raw)
    sub_sorted = sorted(sub_counts.items(), key=lambda kv: kv[1])
    pretty_sub = {
        "domo_volcanico": "Domo volcánico",
        "albardon": "Albardón aluvial",
        "lomada": "Lomada / colina",
        "paleocauce": "Paleocauce",
        "canchal": "Canchal / talud",
        "morrena": "Morrena glaciar",
        "cono_aluvial": "Cono aluvial",
        "escarpa": "Escarpa estructural",
        "medano_fosil": "Médano fósil",
        "geoforma_no_clasificada": "No clasificada",
        "roca_fracturada": "Roca fracturada",
    }

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(13.8, 4.6), gridspec_kw={"width_ratios": [1.05, 1.05, 1.0], "wspace": 0.52})

    # Panel A
    y1 = np.arange(len(order_types))
    ax1.barh(y1, nat_vals, color="#2A9D8F", height=0.58, label=f"NATURAL (N={sum(nat_vals)})")
    ax1.barh(y1, art_vals, left=nat_vals, color="#E76F51", height=0.58, label=f"ARTEFACTO (N={sum(art_vals)})")
    for idx, (nv, av) in enumerate(zip(nat_vals, art_vals)):
        tot = nv + av
        ax1.text(tot + 0.8, idx, f"{tot} ({100*tot/len(desc_raw):.1f}%)", va="center", fontsize=7.8, fontweight="bold", color="#1E293B")
    ax1.set_yticks(y1)
    ax1.set_yticklabels([pretty_types.get(k, k) for k in order_types], fontsize=8.2)
    ax1.set_xlim(0, 52)
    ax1.set_xlabel("Anomalías auditadas (N = 121)")
    ax1.set_title("A. Morfometría vs. Dictamen VLM")
    ax1.grid(axis="x", ls="--", alpha=0.4)
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    ax1.legend(loc="lower right", fontsize=7.6, frameon=True, facecolor="white", edgecolor="#CBD5E1")
    ax1.text(
        0.98,
        0.24,
        f"Relieve (+): {pos_cnt}\nRelieve (-): {neg_cnt}\nConfirmadas: 0",
        transform=ax1.transAxes,
        ha="right",
        va="bottom",
        fontsize=7.3,
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#F8FAFC", edgecolor="#CBD5E1"),
    )

    # Panel B
    y2 = np.arange(len(sub_sorted))
    vals2 = [v for _, v in sub_sorted]
    labels2 = [pretty_sub.get(k, k) for k, _ in sub_sorted]
    cols2 = []
    for k, _ in sub_sorted:
        if k in ("domo_volcanico", "canchal", "roca_fracturada", "escarpa"):
            cols2.append("#1B365D")
        elif k in ("albardon", "paleocauce", "cono_aluvial"):
            cols2.append("#457B9D")
        elif k in ("morrena", "medano_fosil", "lomada"):
            cols2.append("#2A9D8F")
        else:
            cols2.append("#8D99AE")
    ax2.barh(y2, vals2, color=cols2, height=0.65)
    for idx, val in enumerate(vals2):
        ax2.text(val + 0.3, idx, str(val), va="center", fontsize=7.8, color="#1E293B")
    ax2.set_yticks(y2)
    ax2.set_yticklabels(labels2, fontsize=8.0)
    ax2.set_xlim(0, max(vals2) + 3.5)
    ax2.set_xlabel(f"Geoformas catalogadas (N = {len(inv_raw)})")
    ax2.set_title("B. Inventario Geomorfológico Secundario")
    ax2.grid(axis="x", ls="--", alpha=0.4)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    geo_handles = [
        mpatches.Patch(color="#1B365D", label="Volcánica / lítica / escarpa"),
        mpatches.Patch(color="#457B9D", label="Fluvial / aluvial"),
        mpatches.Patch(color="#2A9D8F", label="Glacial / eólica / colinar"),
        mpatches.Patch(color="#8D99AE", label="No clasificada"),
    ]
    ax2.legend(handles=geo_handles, loc="lower right", fontsize=6.9, frameon=True, facecolor="white", edgecolor="#CBD5E1")

    # Panel C
    all_cert = cert_nat + cert_art
    all_dz = dz_nat + dz_art
    ax3.scatter(dz_nat, cert_nat, color="#2A9D8F", alpha=0.75, s=28, edgecolor="white", lw=0.4, label="NATURAL (N=98)")
    ax3.scatter(dz_art, cert_art, color="#E76F51", marker="s", alpha=0.85, s=30, edgecolor="white", lw=0.4, label="ARTEFACTO (N=23)")
    mean_c = float(np.mean(all_cert))
    med_dz = float(np.median(all_dz))
    ax3.axhline(mean_c, color="#1B365D", ls="--", lw=1.0, label=f"Certeza media: {mean_c:.1f}%")
    ax3.axvline(med_dz, color="#475569", ls=":", lw=1.0, label=f"|dZ| mediana: {med_dz:.2f} m")
    ax3.set_xlim(0.0, 3.0)
    ax3.set_ylim(83.5, 99.5)
    ax3.set_xlabel("Amplitud microtopográfica |dZ| SLRM [m]")
    ax3.set_ylabel("Certeza pericial VLM [%]")
    ax3.set_title("C. Amplitud Vertical vs. Certeza VLM")
    ax3.grid(ls="--", alpha=0.35)
    ax3.spines["top"].set_visible(False)
    ax3.spines["right"].set_visible(False)
    ax3.legend(loc="lower right", fontsize=7.2, frameon=True, facecolor="white", edgecolor="#CBD5E1")

    save_dual(fig, "fig4_campaign_results_and_geoforms")


def main() -> None:
    setup_pub_style()
    make_fig2_national_coverage_map()
    make_fig3_scale_and_ml()
    make_fig4_campaign_results()
    print("All figures generated successfully.")


if __name__ == "__main__":
    main()

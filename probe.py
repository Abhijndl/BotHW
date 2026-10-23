#!/usr/bin/env python3
"""Probe #30: FirstCry's checkout cart call (ShoppingCart.svc/json/LoadCart — what
checkout.firstcry.com sends for a guest; a guest cart is only a cookie string,
nothing is stored or ordered). Does it say "can't be delivered to 248001" per
car, and can one call check many cars?"""
import json, time, uuid
from curl_cffi import requests as http

T0 = time.time()
IMP = {"impersonate": "chrome124"}
UA = ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36")
URL = "https://CSC.fcappservices.in/ShoppingCart/ShoppingCart.svc/json/LoadCart"
REPORT = {}
CARS = {"24783699": "AAR Cuda (cart said: Cannot be delivered to 248001, 13:32)",
        "24473712": "Salt Streaker (common)", "24783759": "DB5 Safari (sold out?)",
        "24776090": "Lucid Air (stuck page 0)", "24473731": "Road Runner"}
KEYF = ("ProductID", "ProductName", "Quantity", "CurrentStock", "IsServicable", "NoOfPinCodeToCheck",
        "isValidPincodeForDropShipment", "NextDayDelivery", "SameDayDelivery", "StockType", "DispatchTAT",
        "derived_pincode", "ServiceableProductIds", "ShipBy", "qwikstores", "status", "stock", "TATObj",
        "RestrictedQty", "IsCODAllowed", "OfferType", "ActualPrice")


def body(pro, pin, lt="N"):
    return {"pro": pro, "shipPin": pin, "SiteType": 0, "LC": 0, "CR": 0, "Coupons": "", "FC_AUTH": "",
            "ShipMobile": "", "ShipPhone": "", "PayBack": "", "State": "", "PaymentType": "", "LPO": False,
            "LSD": False, "CCA": "", "LT": lt, "UA": UA + " Mobile", "AddressType": "Home", "AssemblyMap": "",
            "ptype": "", "pvalue": "", "FitKidChildIdMap": "", "CouponCodeToCheck": "", "GiftCodeToCheck": "",
            "BuyerType": "", "CardPar": "", "RemoveFreeErr": "", "redesign": True, "caller": "", "Ageid": "",
            "bmsm": "", "SegmentIDs": "", "latlong": "", "segmentcookie": "", "cardref": "",
            "savedCardBankCode": "", "savedCardIssuingBank": "", "cardtoken": ""}


H = {"User-Agent": UA, "Accept": "application/json, text/javascript, */*; q=0.01",
     "Content-Type": "application/json; charset=utf-8", "Origin": "https://checkout.firstcry.com",
     "Referer": "https://checkout.firstcry.com/pay", "fcdid": str(uuid.uuid4()), "fingerprint": uuid.uuid4().hex}


def call(pro, pin, label):
    try:
        r = http.post(URL, data=json.dumps(body(pro, pin)), headers=H, timeout=25, **IMP)
    except Exception as e:
        print(f"{label}: ERR {e}")
        return None
    t = r.text
    try:
        d = json.loads(t)
        while isinstance(d, str):
            d = json.loads(d)
    except Exception:
        d = None
    print(f"\n--- {label}: HTTP {r.status_code}, {len(t)} b")
    if not isinstance(d, dict):
        print("   ", t[:1500])
        return None
    REPORT[label] = d
    res = d.get("LoadCartResult") or d.get("GetCartResult") or d
    if isinstance(res, str):
        try:
            res = json.loads(res)
        except Exception:
            pass
    summ = (res or {}).get("pOrderSummary") if isinstance(res, dict) else None
    print("    top keys:", list((res or {}).keys())[:20] if isinstance(res, dict) else type(res))
    if isinstance(summ, dict):
        print("    summary:", {k: summ.get(k) for k in ("ShipPinCode", "TotalProducts", "TotalItems", "NetPayment")})
        for it in summ.get("PurchaseOrderItemList") or []:
            print("    item:", json.dumps({k: it.get(k) for k in KEYF if k in it})[:1200])
            other = {k: v for k, v in it.items() if k not in KEYF and v not in (None, "", 0, False, [], {})}
            print("       other:", json.dumps(other)[:1500])
    else:
        print("   ", json.dumps(d)[:2000])
    return d


for pid, nm in CARS.items():
    call(f"NO^{pid}^1^0", "248001", f"{pid} {nm} @248001")
    time.sleep(0.4)
call("NO^24783699^1^0", "110001", "AAR Cuda @110001 (Delhi)")
call("*".join(f"NO^{p}^1^0" for p in CARS), "248001", "all five in one cart @248001")
json.dump(REPORT, open("probe_report.json", "w"))
print(f"\ndone in {time.time() - T0:.0f}s")

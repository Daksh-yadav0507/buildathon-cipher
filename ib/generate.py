"""The three made-up phones (section 4): a gold-smuggling story planted in five months of everyday noise.

Everything here is invented: the people, numbers, banks, companies and places' labels. One random.Random(2026)
drives every choice, so every run writes byte-identical files:

    data/samples/phone1.json  Vikram Mehra  (iPhone backup)       about 9,000 records
    data/samples/phone2.json  Raju Verma    (Android backup)      about 6,000 records
    data/samples/phone3.json  Meena Iyer    (phone-reader report) about 5,000 records

samples() lists them for /api/samples; ensure_samples() writes any that are missing or out of date.
Run `.venv/bin/python -m ib.generate [folder]` to write them (default: the data folder's samples/).
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

GEN_VERSION = "ib-sample-3"
IST = timezone(timedelta(hours=5, minutes=30))
SAMPLE_NAMES = ("phone1", "phone2", "phone3")
TARGETS = {1: 9000, 2: 6000, 3: 5000}

START_DAY = datetime(2026, 6, 1, tzinfo=IST)
END_DAY = datetime(2026, 11, 15, tzinfo=IST)

# ---------------------------------------------------------------- the people (all made up)

V, R, M = "+919810047123", "+919899512640", "+919717033851"
BHAI = "+971506124471"
SAMEER, SONU, DEEPAK = "+919811208834", "+919871455019", "+919958320417"
KIRTI = "+919825061738"
NEHA, MAA, ROHIT = "+919810566290", "+919811730045", "+919899101266"
AJAY, MUMMY, PINKY = "+919711842203", "+919711500864", "+919650211437"
PRIYA, APPA, AMMA, KARTHIK = "+919650773118", "+919840123657", "+919840123658", "+919884420917"

NAMES = {  # the real (made-up) name behind each number
    V: "Vikram Mehra", R: "Raju Verma", M: "Meena Iyer", BHAI: "Bhai Dubai", SAMEER: "Sameer Kapoor",
    SONU: "Sonu", DEEPAK: "Deepak", KIRTI: "Kirti Angadia", NEHA: "Neha Mehra", MAA: "Maa",
    ROHIT: "Rohit", AJAY: "Ajay Verma", MUMMY: "Mummy", PINKY: "Pinky Verma", PRIYA: "Priya",
    APPA: "Appa", AMMA: "Amma", KARTHIK: "Karthik Iyer",
}

AIRPORT_V = (28.5562, 77.0999)
AIRPORT_R = (28.5549, 77.1018)
CARGO_PLACE = "Near the airport cargo terminal, New Delhi"
INVOICE_OCR = "INVOICE No 4471 | Sky Route Logistics | Electronic parts | Declared value Rs 1,20,000"
BE_TEXT = ("Bill of Entry 2026/0915 | Air Cargo Complex, New Delhi | Importer: Sky Route Logistics | "
           "Assessable value 1,20,000 | Duty paid 33,600 | Description: electronic parts | Qty 12 cartons")

# ---------------------------------------------------------------- the line bank

FAMILY = [
    "khana kha liya?", "kab tak aaoge ghar?", "aaj dinner mein kya banau?", "doodh le aana aate hue",
    "Maa ki dawai khatam ho gayi hai", "bacchon ki school fees kal tak jama karni hai", "kal Mamaji aa rahe hain",
    "sabzi wala aaya tha, 200 ke paise diye", "pese rakh diye hain almari mein", "AC service wala kab aayega?",
    "gas cylinder book kar do please", "ghar pe sab theek hai", "thoda jaldi aa jana aaj", "baarish ho rahi hai, chhata le jana",
    "neend aa rahi hai, good night", "Papa ka phone aaya tha", "kal subah 7 baje uthna hai", "bijli ka bill aaya hai",
    "school se call aaya tha PTM ke liye", "fridge mein paneer rakha hai", "main market ja rahi hoon",
    "chai bana doon?", "kitne baje pahunchoge?", "aaj late ho jaayega kya?", "dhyan se gaadi chalana",
    "Riya ka birthday gift lena hai", "online order kar diya, kal aayega", "Maa ne yaad kiya", "weekend pe kahin chalein?",
    "rishtedaar aa rahe hain Sunday ko", "paisa transfer kar dena kaamwali ka", "aaj office mein kya hua?",
    "kal ka plan cancel", "doctor wali appointment shift ho gayi", "garam paani nahi aa raha", "mobile recharge kar do mera",
    "thak gaya hoon aaj", "dawai time pe le lena", "aate hue atta le aana 10 kilo", "sab log so gaye",
    "kal kaam wali nahi aayegi", "ghar ki chabi padosi ke paas hai", "aaj rajma chawal bana hai",
]
FRIENDS = [
    "bhai kya scene hai aaj?", "bro match dekha kal ka?", "bhaiya kal milte hain", "chal chai peete hain",
    "kitna run banaya tune?", "Sunday ko ground booked hai 7 baje", "kaun kaun aa raha hai?", "mai to aa raha hoon pakka",
    "bhai paise wapas kab karega?", "500 bhej de yaar, kal de dunga", "pese kal bhej dunga bro", "movie chalein weekend?",
    "kya bakwas umpiring thi", "last over mein maza aa gaya", "bhai kal ki party mast thi", "photo bhej de group pe",
    "abe phone kyun nahi utha raha", "sorry yaar meeting mein tha", "gym chal raha hai na kal?", "bro naya phone liya kya?",
    "haha sahi hai", "pagal hai kya", "chalo theek hai", "bhaiya jaldi aao, sab wait kar rahe", "kal shaam free hai?",
    "biryani khani hai aaj", "traffic bahut hai yaar", "pahunch gaya, gate pe hoon", "bhai happy birthday, party kab?",
    "aaj nahi ho payega bro", "toss jeet gaye", "Rohit ne century maari", "net practice kal subah",
]
WORK = [
    "meeting 11 baje shift ho gayi", "report bhej do aaj shaam tak", "client ne payment kab tak bola?", "kal office band hai",
    "GST ka kaam pending hai", "invoice ki copy mail kar do", "bank jaana hai cheque jama karne", "sir leave chahiye kal",
    "aaj WFH kar raha hoon", "stock check karna hai godown mein", "driver ko bol do 9 baje", "quotation final ho gaya",
    "purchase order aa gaya", "accounts reconcile karne hain", "Monday tak ho jayega", "courier aaya tha office mein",
    "salary credit ho gayi", "TDS ka challan bana do", "kal audit wale aa rahe hain", "printer phir kharab hai",
    "sab files folder mein daal di", "client call 4 baje", "transport wala late hai", "bill ka payment ho gaya",
    "excel sheet update kar di", "shift roster aa gaya", "overtime milega kya is baar?", "supervisor ne bulaya hai",
    "loading 6 baje shuru hogi", "aaj duty double hai", "canteen band hai aaj",
]
SOCIETY = [
    "Society meeting Sunday 11 am, clubhouse mein", "paani ki tanki ki safai kal hogi", "lift kharab hai B block ki",
    "maintenance 30 tarikh tak jama karein", "kisi ki gaadi gate ke saamne khadi hai", "guard ko bata diya hai",
    "parking stickers office se le lein", "mosquito fogging aaj shaam 6 baje", "power cut 2 se 4 baje tak",
    "Ganpati pandal ke liye chanda", "Diwali mela ki taiyari", "naye residents ka swagat", "plumber ka number chahiye kisi ke paas?",
    "gate ka time 11 baje tak", "dhanyavaad sabka", "kal kooda gaadi nahi aayegi", "pet owners please leash use karein",
    "bacchon ke liye drawing competition", "water bill ka hisaab group pe daal diya", "CCTV lag gaye hain gate pe",
]
GENERAL = [
    "ok", "theek hai", "haan", "nahi yaar", "accha", "hmm", "kal baat karte hain", "call karta hoon thodi der mein",
    "busy hoon abhi", "pahunch ke batata hoon", "sahi hai", "ji", "bilkul", "dekhte hain", "pakka", "achha theek hai",
    "kal pakka", "thik h", "ha bhai", "nai", "kab?", "kahan ho?", "aa raha hoon", "5 min", "location bhejo",
]
ENGLISH = [
    "Good morning!", "Have a great day", "Call me when free", "On my way", "Reached safely", "Thanks a lot",
    "See you tomorrow", "Sounds good", "Running 10 minutes late", "Can we talk later?", "Happy birthday! Have a blast",
    "Congratulations on the new job", "Please send the documents", "Noted, will do", "Sure, no problem",
    "Where are you?", "Let me check and get back", "That's great news", "Take care", "Sorry, missed your call",
    "Meeting at 3 pm", "The file is attached", "Please confirm by evening", "I will be there by 7",
    "Let's catch up this weekend", "Weather is lovely today", "Stuck in traffic", "Dinner at 8?", "Book the tickets",
    "Thanks for the update", "Please review and revert", "Payment done, please check", "Got it", "Will call you back",
    "Happy Independence Day", "Best wishes to the family", "Kindly share the bill", "Is the shop open today?",
    "Order delivered?", "Please pick up the parcel", "Battery low, will call later", "Good night", "Same to you",
    "Can you send the address?", "Lunch was great", "Talk soon", "All set for tomorrow", "Nice photo",
    "Let me know", "Please share the receipt", "The meeting is postponed", "Hope you are well", "Cheers",
    "That works for me", "Bring the charger", "Parking is full", "Leaving now", "Almost there", "Thank you sir",
    "Monthly accounts are done", "Bank statement attached",
]
HINDI = [
    "कल मिलते हैं", "खाना खा लिया?", "पैसे भेज दिए हैं", "ठीक है भाई", "घर कब आओगे?", "माँ की तबीयत ठीक है",
    "सुबह जल्दी उठना है", "कल बात करते हैं", "आज बहुत गर्मी है", "धन्यवाद जी", "बहुत अच्छा", "शाम को फोन करना",
    "राम राम भैया", "दवाई ले ली?", "अभी आ रहा हूँ", "कल छुट्टी है", "पैसे कल दे दूँगा", "शुभ प्रभात",
    "जन्मदिन की बधाई", "दिवाली की शुभकामनाएं", "गणपति बप्पा मोरया", "खाना ठंडा हो रहा है", "बारिश हो रही है",
    "कल सुबह मिलना", "सब ठीक है", "बच्चे स्कूल गए", "बिजली चली गई", "रात को देर हो जाएगी", "आप कहाँ हो?",
    "नमस्ते जी", "बहुत थक गया हूँ",
]
FORWARDS = [
    "Good morning! Aapka din shubh ho", "Subah ki chai aur aapki muskaan, good morning ji", "Good morning, stay blessed",
    "Suprabhat! Har din ek naya mauka hai", "Good morning friends, keep smiling", "शुभ प्रभात, आपका दिन मंगलमय हो",
    "Forwarded: Lemon paani peene ke 10 fayde", "Forwarded: Yeh video zaroor dekhein", "Good night, sweet dreams",
]
GANESH = ["Ganpati Bappa Morya!", "pandal mein aarti 8 baje", "modak bana rahe hain ghar pe", "visarjan kal hai",
          "Ganesh Chaturthi ki hardik shubhkamnaye"]
DIWALI = ["Happy Diwali to you and family", "Diwali ki shopping karni hai", "mithai le aana", "rangoli bana li",
          "patakhe mat jalana zyada", "Dhanteras pe kuch lena hai?", "Diwali bonus aaya kya?", "diye jala diye"]

# network lines (late night) and the code words in context: biscuit, chai pani, packet, maal, doctor sahab, token
NET_PLAIN = [
    "jaag rahe ho?", "call karo free hoke", "kal baat karte hain is baare mein", "sab set hai", "phone pe baat nahi",
    "signal pe aa jao", "kal subah tak ho jayega", "koi problem to nahi?", "dhyan se", "theek hai, kal dekhte hain",
    "flight schedule bhejo", "kitne baje landing hai?", "gate pe kaun hoga?", "naya banda hai, bharosa nahi",
    "aaj nahi, kal", "hisaab baad mein", "apna number badal lo", "zyada baat mat karo", "ok bhai", "ho gaya",
]
NET_CODE = {
    "biscuit": ["is baar 2 biscuit hain", "biscuit safe pahunch gaye", "biscuit ka rate kya chal raha hai?",
                "agle mahine 6 biscuit chahiye", "biscuit ginti mein kam the", "biscuit wale ko bol do ready rahe"],
    "chai pani": ["chai pani ka intezaam kar dena", "gate wale ko chai pani de dena", "chai pani alag se dena hai",
                  "chai pani mein 10 lagenge", "chai pani ho gaya"],
    "packet": ["packet mil gaya?", "packet seal tha na?", "packet ko locker mein rakho", "do packet aayenge is baar",
               "packet kal subah utha lena"],
    "maal": ["maal clear ho gaya", "maal kab tak aayega?", "maal godown mein mat rakhna", "maal ki photo mat lena",
             "maal ka hisaab bhejo", "maal pahunch gaya bhai"],
    "doctor sahab": ["doctor sahab se baat ho gayi", "doctor sahab ka hissa alag", "doctor sahab is hafte chhutti pe hain",
                     "doctor sahab ne naya banda bheja hai", "doctor sahab ko time pe dena"],
    "token": ["token ki photo bhejo", "token ka number match karna", "token wala note sambhal ke", "naya token bhejo",
              "token dikha ke le lena"],
}
CHA_LINES = ["BE file ho gaya", "customs query aayi hai", "consignment ka AWB number bhejo", "examination kal hoga",
             "duty challan bhej diya", "warehouse rent pending hai", "IGM number aa gaya", "out of charge mil gaya",
             "documents original chahiye", "shipping bill check kar lo"]
VM_WORK = ["sir GST ki entry kar di", "is mahine ka hisaab bhej diya", "Sky Route ka bill aaya hai", "cash book update hai",
           "bank statement mail kiya", "sir vendor payment pending hai", "salary sheet ready hai", "TDS file kar diya",
           "invoice number 4402 ka payment aaya", "sir audit ke liye files chahiye"]

APP_DEVICE = {
    1: {"label_owner": "Vikram", "model": "iPhone 15 Pro", "os": "iOS 18.6", "platform": "iphone-backup",
        "file_name": "Vikram_iPhone15Pro_backup_2026-11-16.zip", "imei": "35 291611 482913 6",
        "sims": [{"number": "+91 98100 47123", "carrier": "Airtel"}],
        "accounts": [{"kind": "Apple ID", "id": "vikram.m@mailbox.example"}, {"kind": "WhatsApp", "id": V},
                     {"kind": "Telegram", "id": "@vm_imports"}, {"kind": "Signal", "id": V}],
        "wifi": [{"ssid": "Mehra_Home_5G", "last_seen": "2026-11-15"}, {"ssid": "MehraImports-Office", "last_seen": "2026-11-14"},
                 {"ssid": "Airport_Free_WiFi", "last_seen": "2026-09-15"}],
        "apps": [{"name": "WhatsApp", "version": "25.20.1"}, {"name": "Telegram", "version": "11.4"},
                 {"name": "Signal", "version": "7.31"}, {"name": "BUB Mobile", "version": "6.2"},
                 {"name": "Google Maps", "version": "6.140"}]},
    2: {"label_owner": "Raju", "model": "Samsung Galaxy A55", "os": "Android 15", "platform": "android-backup",
        "file_name": "Raju_GalaxyA55_backup_2026-11-16.tar", "imei": "35 884210 776120 4",
        "sims": [{"number": "+91 98995 12640", "carrier": "Jio"}],
        "accounts": [{"kind": "Google", "id": "raju.verma92@mailbox.example"}, {"kind": "WhatsApp", "id": R}],
        "wifi": [{"ssid": "Verma_Home", "last_seen": "2026-11-15"}, {"ssid": "Cargo-Staff", "last_seen": "2026-11-15"}],
        "apps": [{"name": "WhatsApp", "version": "2.25.20"}, {"name": "Sapphire Bank", "version": "4.8"},
                 {"name": "Telegram", "version": "11.4"}, {"name": "Google Maps", "version": "11.140"}]},
    3: {"label_owner": "Meena", "model": "Redmi Note 13", "os": "Android 14", "platform": "ufdr-report",
        "file_name": "Meena_RedmiNote13_report_2026-11-17.ufdr", "imei": "86 401205 339187 2",
        "sims": [{"number": "+91 97170 33851", "carrier": "Vi"}],
        "accounts": [{"kind": "Google", "id": "meena.iyer.acc@mailbox.example"}, {"kind": "WhatsApp", "id": M}],
        "wifi": [{"ssid": "Iyer_Home", "last_seen": "2026-11-16"}, {"ssid": "Kaveri-Office", "last_seen": "2026-11-14"}],
        "apps": [{"name": "WhatsApp", "version": "2.25.18"}, {"name": "BUB Mobile", "version": "6.2"},
                 {"name": "Signal", "version": "7.30"}, {"name": "Tally Viewer", "version": "2.1"}]},
}
OWNERS = {
    1: {"name": "Vikram Mehra", "numbers": [V], "emails": ["vikram.m@mailbox.example"]},
    2: {"name": "Raju Verma", "numbers": [R], "emails": ["raju.verma92@mailbox.example"]},
    3: {"name": "Meena Iyer", "numbers": [M], "emails": ["meena.iyer.acc@mailbox.example"]},
}
OWNER_NO = {1: V, 2: R, 3: M}
PLACES = {
    1: [("Home, Green Park", 28.5590, 77.2066, 5), ("Office, Karol Bagh", 28.6519, 77.1909, 4),
        ("Saket market", 28.5245, 77.2066, 1), ("Gym, Hauz Khas", 28.5494, 77.2001, 1)],
    2: [("Home, Mahipalpur", 28.5450, 77.1240, 5), ("Airport cargo terminal (work)", 28.5556, 77.1003, 4),
        ("Dwarka market", 28.5921, 77.0460, 1)],
    3: [("Home, Lajpat Nagar", 28.5677, 77.2433, 5), ("Office, Connaught Place", 28.6315, 77.2167, 4),
        ("Nehru Place", 28.5491, 77.2513, 1)],
}


def ms(y, mo, d, h=0, mi=0, s=0) -> int:
    return int(datetime(y, mo, d, h, mi, s, tzinfo=IST).timestamp() * 1000)


def iso(t: int) -> str:
    return datetime.fromtimestamp(t / 1000, IST).isoformat()


class World:
    """Builds all three phones at once so that shared chats and calls land on both phones."""

    def __init__(self):
        self.rng = random.Random(2026)
        self.events = {1: [], 2: [], 3: []}
        self.contacts = {1: {}, 2: {}, 3: {}}   # number -> saved name
        self.convs = {}                          # key -> {app, is_group, participants, titles{phone: title}}
        self.used_numbers = set(NAMES)
        self.counter = 0

    # ------------------------------------------------------------ helpers
    def number(self) -> str:
        while True:
            n = "+91" + self.rng.choice(["98", "99", "97", "96", "88", "87", "70", "93"]) + "".join(
                str(self.rng.randrange(10)) for _ in range(8))
            if n not in self.used_numbers:
                self.used_numbers.add(n)
                return n

    def sha(self) -> str:
        return "%064x" % self.rng.getrandbits(256)

    def phones_of(self, number):
        return [p for p, o in OWNER_NO.items() if o == number]

    def conv(self, key, app, participants, titles, is_group=False):
        if key not in self.convs:
            self.convs[key] = {"key": key, "app": app, "is_group": is_group, "participants": list(participants),
                               "titles": dict(titles)}
        return key

    def pair_key(self, app, a, b):
        x, y = sorted([a, b])
        return f"{app}:{x}|{y}"

    def add(self, phone, **ev):
        self.counter += 1
        base = {"kind": "message", "app": "whatsapp", "ts": 0, "direction": "", "sender": "", "recipients": [],
                "conv": None, "body": "", "status": "", "duration_s": None, "lat": None, "lon": None, "place": None,
                "media_name": None, "media_size": None, "media_sha256": None, "transcript": None, "ocr_text": None,
                "extra": None, "_seq": self.counter}
        base.update(ev)
        self.events[phone].append(base)
        return base

    def say(self, key, ts, sender, body, kind="message", status=None, only=None, **kw):
        """One message in a chat, on every seized phone that is part of it (with the right direction)."""
        c = self.convs[key]
        out = []
        for p in (1, 2, 3):
            if OWNER_NO[p] not in c["participants"] or p not in c["titles"]:
                continue
            if only and p not in only:
                continue
            st = (status or {}).get(p, "")
            rec = [x for x in c["participants"] if x != sender]
            lag = 0 if sender == OWNER_NO[p] else 1000 * self.rng.randrange(0, 3)
            out.append(self.add(p, kind=kind, app=c["app"], ts=ts + lag, direction="out" if sender == OWNER_NO[p] else "in",
                                sender=sender, recipients=rec, conv=key, body=body, status=st, **kw))
        return out

    def call(self, phones, ts, caller, callee, app, duration, missed=False):
        for p in phones:
            me = OWNER_NO[p]
            out = caller == me
            st = "missed" if (missed and not out) else ""
            self.add(p, kind="call", app=app, ts=ts, direction="out" if out else "in", sender=caller,
                     recipients=[callee], body="", status=st, duration_s=0 if missed else duration)

    # ------------------------------------------------------------ time
    def day(self, start=START_DAY, end=END_DAY, sep_boost=1.0):
        n = (end - start).days + 1
        while True:
            d = start + timedelta(days=self.rng.randrange(n))
            if d.month == 9 and sep_boost > 1 and self.rng.random() > 1 / sep_boost:
                return d
            if d.month != 9 or self.rng.random() < 1.0:
                return d

    DAY_HOURS = [0.2, 0.1, 0.05, 0.05, 0.05, 0.2, 0.6, 1.5, 2.5, 3, 3.2, 3.2, 3, 2.6, 2.4, 2.4, 2.6, 2.8, 3, 3.2, 3.2, 2.8, 1.8, 0.8]
    NIGHT_HOURS = [3.5, 1.5, 0.5, 0.1, 0.05, 0.05, 0.05, 0.1, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.3, 0.4, 0.6, 0.8, 1.5, 4, 4.5]

    def when(self, night=False, start=START_DAY, end=END_DAY, avoid=None):
        hours = self.NIGHT_HOURS if night else self.DAY_HOURS
        while True:
            d = self.day(start, end)
            h = self.rng.choices(range(24), weights=hours)[0]
            t = d + timedelta(hours=h + (24 if night and h < 6 else 0), minutes=self.rng.randrange(60),
                              seconds=self.rng.randrange(60))
            if t > END_DAY + timedelta(days=1):
                continue
            tm = int(t.timestamp() * 1000)
            if avoid and any(a <= tm < b for a, b in avoid):
                continue
            return tm

    def line(self, pools, ts):
        d = datetime.fromtimestamp(ts / 1000, IST)
        if d.month == 9 and 10 <= d.day <= 24 and self.rng.random() < 0.08:
            return self.rng.choice(GANESH)
        if (d.month == 10 and d.day >= 25 or d.month == 11 and d.day <= 12) and self.rng.random() < 0.1:
            return self.rng.choice(DIWALI)
        names, weights = zip(*pools)
        return self.rng.choice(self.rng.choices(names, weights=weights)[0])


# ---------------------------------------------------------------- the planted story (section 4.3)

def plant(w: World):
    # saved names (4.3 #10) and the network contacts
    w.contacts[1].update({R: "Raju Flight", M: "Meena Iyer", BHAI: "Bhai Dubai", SAMEER: "Sameer CHA", SONU: "Sonu Cargo",
                          DEEPAK: "Deepak", NEHA: "Neha", MAA: "Maa", ROHIT: "Rohit"})
    w.contacts[2].update({V: "Vikram Sir", SONU: "Sonu", DEEPAK: "Deepak Bhai", AJAY: "Ajay Bhai", MUMMY: "Mummy", PINKY: "Pinky"})
    w.contacts[3].update({V: "VM Accounts", KIRTI: "Kirti Angadia", PRIYA: "Priya Office", APPA: "Appa", AMMA: "Amma",
                          KARTHIK: "Karthik"})

    vb = w.conv(w.pair_key("whatsapp", V, BHAI), "whatsapp", [V, BHAI], {1: "Bhai Dubai"})
    vr = w.conv(w.pair_key("whatsapp", V, R), "whatsapp", [V, R], {1: "Raju Flight", 2: "Vikram Sir"})
    vm = w.conv(w.pair_key("whatsapp", V, M), "whatsapp", [V, M], {1: "Meena Iyer", 3: "VM Accounts"})
    mk = w.conv(w.pair_key("whatsapp", M, KIRTI), "whatsapp", [M, KIRTI], {3: "Kirti Angadia"})
    ct = w.conv("whatsapp-group:cargo-team", "whatsapp", [V, R, SONU, DEEPAK], {1: "Cargo Team", 2: "Cargo Team"}, True)

    # 1. 12 Sep 11:52 pm, Bhai Dubai -> Vikram
    w.say(vb, ms(2026, 9, 12, 23, 52, 8), BHAI, "agle hafte 4 biscuit bhej raha hoon, pakka")
    w.say(vb, ms(2026, 9, 12, 23, 55, 40), V, "theek hai bhai, Raju ko bol dunga")
    w.say(vb, ms(2026, 9, 15, 23, 58, 2), V, "sab utar gaya bhai, kal hisaab")
    w.say(vb, ms(2026, 9, 16, 23, 14, 51), BHAI, "pachaas de diye na usko?")
    w.say(vb, ms(2026, 9, 16, 23, 16, 5), V, "haan subah hi")

    # 2-6. the Vikram-Raju chat of 14-17 Sep: 37 messages and a voice note, all deleted (recovered) on Raju's phone
    dl = {2: "deleted"}
    vr_lines = [
        ((14, 22, 24, 10), V, "jaag rahe ho?"), ((14, 22, 25, 2), R, "haan sir, bolo"),
        ((14, 22, 31, 0), V, "kal raat XY-512 aa rahi hai Dubai se. gate 4 ke paas wait karna, packet do hisse mein hoga"),
        ((14, 22, 34, 30), R, "samajh gaya sir. gate 4 pe kitne baje?"), ((14, 22, 35, 12), V, "11:30 ke baad. landing 11:05 hai"),
        ((14, 22, 36, 40), R, "theek hai. Sonu ko bata doon?"), ((14, 22, 37, 15), V, "main bata dunga. tum bas time pe rehna"),
        ((14, 22, 39, 1), R, "ok sir"), ((14, 22, 51, 33), V, "apna duty roster check kar lena, kal raat ki shift tumhari hai na?"),
        ((14, 22, 53, 9), R, "haan sir, B shift, 8 se 8"), ((14, 22, 54, 0), V, "badhiya"),
        ((15, 19, 12, 44), V, "aaj ka plan yaad hai na"), ((15, 19, 15, 3), R, "haan sir, ready hoon"),
        ((15, 21, 48, 20), V, "flight on time hai, check kiya"), ((15, 21, 50, 7), R, "ok"),
        ((15, 23, 5, 30), R, "landing ho gayi sir"), ((15, 23, 18, 2), R, "maal utar raha hai, belt 3"),
        ((15, 23, 26, 45), V, "main bahar hoon, cargo gate ke paas"), ((15, 23, 33, 10), R, "do minute"),
        ((15, 23, 47, 51), R, "dono hisse nikal gaye, Sonu ke paas ek"), ((15, 23, 49, 20), V, "shabash. ab ghar jao"),
        ((16, 0, 21, 4), R, "pahunch gaya sir"), ((16, 9, 58, 40), V, "paise bhej raha hoon abhi"),
        ((16, 10, 9, 0), R, "pachaas mil gaye bhai"), ((16, 10, 11, 18), V, "theek hai. baaki baad mein"),
        ((16, 10, 12, 2), R, "ji sir"), ((16, 21, 40, 10), V, "free ho to call karta hoon"),
        ((16, 21, 41, 30), R, "haan sir 10 baje ke baad"), ((16, 22, 21, 0), V, "jo bola woh yaad rakhna"),
        ((16, 22, 22, 14), R, "haan sir pakka"), ((17, 7, 58, 3), V, "uthe?"), ((17, 8, 1, 40), R, "haan sir"),
        ((17, 8, 14, 0), V, "group dekho abhi"), ((17, 8, 16, 22), R, "dekh liya sir, kar raha hoon"),
        ((17, 8, 17, 5), V, "is chat ko bhi saaf karo"), ((17, 8, 18, 30), R, "ok sir"), ((17, 8, 20, 0), V, "theek."),
    ]
    assert len(vr_lines) == 37
    for (d, h, mi, s), who, body in vr_lines:
        w.say(vr, ms(2026, 9, d, h, mi, s), who, body, status=dl)
    vsha = w.sha()
    for p, name in ((1, "Audio_2026-09-14_223214.opus"), (2, "PTT-20260914-WA0007.opus")):
        w.say(vr, ms(2026, 9, 14, 22, 32, 14), V, "", kind="voice", status=dl, only=[p], duration_s=9,
              media_name=name, media_size=14_820, media_sha256=vsha,
              transcript="ek hissa tum lena, ek Sonu. kisi ko phone mat karna")

    # Cargo Team group around the night and the raid message (6)
    w.say(ct, ms(2026, 9, 15, 21, 30, 0), V, "aaj raat sab alert rehna. Raju gate 4, Sonu bahar gaadi mein")
    w.say(ct, ms(2026, 9, 15, 21, 31, 44), SONU, "ok bhai")
    w.say(ct, ms(2026, 9, 15, 21, 33, 2), DEEPAK, "main kal subah godown pe")
    w.say(ct, ms(2026, 9, 17, 8, 12, 0), V, "sab chat delete kar do abhi. raid ki khabar hai")
    w.say(ct, ms(2026, 9, 17, 8, 13, 10), SONU, "ok bhai")
    w.say(ct, ms(2026, 9, 17, 8, 15, 2), R, "ok sir")
    w.say(ct, ms(2026, 9, 17, 8, 15, 49), DEEPAK, "kar diya")

    # 3. 15 Sep 11:40 pm, both phones at the airport cargo terminal, and Vikram's photo there
    w.add(1, kind="location", app="location", ts=ms(2026, 9, 15, 23, 40, 12), lat=AIRPORT_V[0], lon=AIRPORT_V[1],
          place=CARGO_PLACE, extra={"accuracy_m": 12})
    w.add(2, kind="location", app="location", ts=ms(2026, 9, 15, 23, 44, 30), lat=AIRPORT_R[0], lon=AIRPORT_R[1],
          place=CARGO_PLACE, extra={"accuracy_m": 18})
    w.add(1, kind="photo", app="camera", ts=ms(2026, 9, 15, 23, 41, 3), direction="out", sender=V, lat=AIRPORT_V[0] + 0.0001,
          lon=AIRPORT_V[1] + 0.0002, place=CARGO_PLACE, media_name="IMG_4398.jpg", media_size=2_874_112,
          media_sha256=w.sha(), _named=True)

    # 4. 16 Sep: the ₹50,000 UPI payment, debit on Vikram's phone, credit on Raju's two minutes later
    w.conv(f"sms:{V}|AD-BUBANK", "sms", [V, "AD-BUBANK"], {1: "AD-BUBANK"})
    w.conv(f"sms:{R}|VM-SPHBNK", "sms", [R, "VM-SPHBNK"], {2: "VM-SPHBNK"})
    w.say(f"sms:{V}|AD-BUBANK", ms(2026, 9, 16, 10, 5, 0), "AD-BUBANK",
          "Rs 50,000.00 debited from A/c XX4471 on 16-09-26 by UPI to RAJU VERMA. UPI Ref 624118930551.")
    w.say(f"sms:{R}|VM-SPHBNK", ms(2026, 9, 16, 10, 7, 0), "VM-SPHBNK",
          "Rs 50,000.00 credited to A/c XX2640 on 16-09-26 by UPI from VIKRAM MEHRA. Ref 624118930551.")

    # 5. 16 Sep 10:15 pm, WhatsApp call Vikram -> Raju (4 min 12 s): only on Vikram's log
    w.call([1], ms(2026, 9, 16, 22, 15, 0), V, R, "whatsapp", 252)
    w.call([2], ms(2026, 9, 16, 21, 2, 0), AJAY, R, "phone", 184)
    w.call([2], ms(2026, 9, 16, 23, 30, 0), R, SONU, "whatsapp", 95)

    # 7. 18 Sep 3:20 pm, the invoice photo on Vikram's and Meena's phones, and the "real value"
    isha, isize = w.sha(), 1_946_301
    w.say(vm, ms(2026, 9, 18, 15, 20, 0), V, "", kind="photo", media_name="IMG_4471.jpg", media_size=isize,
          media_sha256=isha, ocr_text=INVOICE_OCR, _named=True)
    w.say(vm, ms(2026, 9, 18, 15, 22, 10), V, "asli value 18 lakh hai, invoice mein 1.2 dikhana hai")
    w.say(vm, ms(2026, 9, 18, 15, 24, 31), M, "ok sir, 1.2 hi dikhaungi")
    # 8. 20 Sep 7:45 pm
    w.say(vm, ms(2026, 9, 20, 19, 45, 0), V, "doctor sahab ko 25 de diya, ab cargo clear hoga")
    w.say(vm, ms(2026, 9, 20, 19, 47, 12), M, "theek hai sir. entry kaise likhun?")
    w.say(vm, ms(2026, 9, 20, 19, 48, 40), V, "consultancy fees likh do")
    # 9. 22 Sep 1:10 pm, Meena and Kirti Angadia, then the bill of entry
    w.say(mk, ms(2026, 9, 22, 13, 10, 0), M, "token: 10 ka note, number 7H 482913. 4 lakh Surat mein dena")
    w.say(mk, ms(2026, 9, 22, 13, 12, 25), KIRTI, "mil gaya. kal shaam tak ho jayega")
    w.add(3, kind="document", app="files", ts=ms(2026, 9, 22, 13, 24, 0), direction="in", media_name="BE_2026_0915.pdf",
          media_size=184_220, media_sha256=w.sha(), ocr_text=BE_TEXT, body="", _named=True)


# ---------------------------------------------------------------- the everyday noise (section 4.4)

def network_noise(w: World):
    rng = w.rng
    vb, vr, vm = w.pair_key("whatsapp", V, BHAI), w.pair_key("whatsapp", V, R), w.pair_key("whatsapp", V, M)
    mk, ct = w.pair_key("whatsapp", M, KIRTI), "whatsapp-group:cargo-team"
    vs = w.conv(w.pair_key("whatsapp", V, SAMEER), "whatsapp", [V, SAMEER], {1: "Sameer CHA"})
    vs_sig = w.conv(w.pair_key("signal", V, SAMEER), "signal", [V, SAMEER], {1: "Sameer CHA"})
    story = [(ms(2026, 9, 13), ms(2026, 9, 19))]
    net_start, net_end = datetime(2026, 7, 5, tzinfo=IST), datetime(2026, 10, 31, tzinfo=IST)

    # code words: each used a set number of times, spread over the network chats
    code_plan = {"biscuit": 9, "chai pani": 8, "packet": 7, "maal": 9, "doctor sahab": 6, "token": 6}
    code_convs = {"biscuit": [vb, vr, ct], "chai pani": [vb, vr, vs, ct], "packet": [vr, ct, vb],
                  "maal": [vr, ct, vb, vs], "doctor sahab": [vm, vs, vb], "token": [mk, vm]}
    for word, n in code_plan.items():
        for _ in range(n):
            key = rng.choice(code_convs[word])
            parts = w.convs[key]["participants"]
            w.say(key, w.when(True, net_start, net_end, story), rng.choice(parts), rng.choice(NET_CODE[word]))

    def chat(key, n, pools, night_share, start=START_DAY, end=END_DAY, avoid=story):
        parts = w.convs[key]["participants"]
        for _ in range(n):
            night = rng.random() < night_share
            t = w.when(night, start, end, avoid)
            body = w.line(pools if not night else [(NET_PLAIN, 3), (GENERAL, 1)], t)
            st = None
            if key not in (vr,) and rng.random() < 0.015:
                st = {rng.choice([1, 2, 3]): "deleted"}
            w.say(key, t, rng.choice(parts), body, status=st)

    chat(vb, 110, [(NET_PLAIN, 1)], 1.0, net_start, net_end)
    chat(vr, 240, [(GENERAL, 3), (FRIENDS, 2), (WORK, 1)], 0.6)
    chat(ct, 140, [(GENERAL, 3), (WORK, 1)], 0.75, net_start, datetime(2026, 11, 10, tzinfo=IST),
         [(ms(2026, 9, 14), ms(2026, 9, 18))])
    chat(vm, 230, [(VM_WORK, 4), (GENERAL, 2), (ENGLISH, 1)], 0.2)
    chat(mk, 70, [(NET_PLAIN, 2), (GENERAL, 1)], 0.8, net_start, net_end)
    chat(vs, 90, [(CHA_LINES, 4), (GENERAL, 1)], 0.35)
    chat(vs_sig, 25, [(CHA_LINES, 2), (NET_PLAIN, 1)], 0.6, net_start, net_end)

    # monthly Vikram -> Meena transfer, on both phones
    w.conv(f"sms:{M}|AD-BUBANK", "sms", [M, "AD-BUBANK"], {3: "AD-BUBANK"})
    for mo in range(6, 12):
        t = ms(2026, mo, 1, 11, rng.randrange(0, 50), rng.randrange(60))
        ref = "6" + "".join(str(rng.randrange(10)) for _ in range(11))
        dd = f"01-{mo:02d}-26"
        w.say(f"sms:{V}|AD-BUBANK", t, "AD-BUBANK", f"Rs 35,000.00 debited from A/c XX4471 on {dd} by UPI to MEENA IYER. UPI Ref {ref}.")
        w.say(f"sms:{M}|AD-BUBANK", t + 60_000 * rng.randrange(1, 3), "AD-BUBANK",
              f"Rs 35,000.00 credited to A/c XX3851 on {dd} by UPI from VIKRAM MEHRA. Ref {ref}.")

    # shared calls (on both logs), Bhai Dubai's late-night calls, Sameer's calls
    for a, b, n in ((V, R, 45), (V, M, 40)):
        for _ in range(n):
            t = w.when(rng.random() < 0.5, avoid=story)
            caller, callee = (a, b) if rng.random() < 0.6 else (b, a)
            missed = rng.random() < 0.12
            w.call(w.phones_of(a) + w.phones_of(b), t, caller, callee, rng.choice(["phone", "whatsapp"]),
                   rng.randrange(20, 600), missed)
    for _ in range(30):
        t = w.when(True, net_start, net_end)
        w.call([1], t, BHAI if rng.random() < 0.6 else V, V if rng.random() < 0.6 else BHAI, "whatsapp", rng.randrange(40, 900))
    for _ in range(25):
        w.call([1], w.when(False), SAMEER, V, "phone", rng.randrange(30, 400), rng.random() < 0.12)
    for _ in range(12):
        w.call([3], w.when(True, net_start, net_end), KIRTI, M, "whatsapp", rng.randrange(30, 300))


def private_noise(w: World, p: int):
    rng = w.rng
    me = OWNER_NO[p]
    people = []   # (number, saved name, pools, weight)
    groups = []   # (key, name, members, pools, weight)

    def person(number, name, pools, weight):
        w.contacts[p].setdefault(number, name)
        people.append((number, w.contacts[p][number], pools, weight))

    fam = [(FAMILY, 5), (GENERAL, 2), (HINDI, 1), (ENGLISH, 1)]
    fri = [(FRIENDS, 5), (GENERAL, 2), (ENGLISH, 1), (HINDI, 0.3)]
    wrk = [(WORK, 4), (GENERAL, 2), (ENGLISH, 2)]
    if p == 1:
        person(NEHA, "Neha", fam, 14); person(MAA, "Maa", [(FAMILY, 3), (HINDI, 3), (FORWARDS, 1)], 6)
        person(ROHIT, "Rohit", fri, 5)
        for nm, pools, wt in (("Kapil Office", wrk, 4), ("Ankit Gupta", fri, 2), ("Vivek CA", wrk, 2), ("Manoj Driver", wrk, 3),
                              ("Pooja Bhabhi", fam, 2), ("Ramesh Kirana", [(GENERAL, 2), (FAMILY, 1)], 1),
                              ("Amit Insurance", [(ENGLISH, 2), (WORK, 1)], 1), ("Tarun", fri, 2), ("Gaurav Gym", fri, 1),
                              ("Sunita Didi", fam, 2), ("Nikhil Bhatia", fri, 1), ("Pappu Plumber", [(GENERAL, 1)], 1)):
            person(w.number(), nm, pools, wt)
        groups.append(("Sunday XI", [ROHIT] + [w.number() for _ in range(7)], [(FRIENDS, 4), (GENERAL, 2)], 7))
        groups.append(("Green Park Society", [w.number() for _ in range(10)], [(SOCIETY, 5), (FORWARDS, 1), (GENERAL, 1)], 6))
        groups.append(("Mehra Parivar", [NEHA, MAA] + [w.number() for _ in range(5)], [(FAMILY, 3), (FORWARDS, 2), (HINDI, 1)], 5))
        sms_ids = [("AD-BUBANK", "bank", 5), ("JD-AIRTEL", "telco", 2), ("AX-FOODIE", "offer", 2), ("BZ-SHOPEE", "delivery", 2),
                   ("TX-QUIKPE", "otp", 2)]
        bank, acct = "Bharat Union Bank", "XX4471"
    elif p == 2:
        person(AJAY, "Ajay Bhai", fam, 6); person(MUMMY, "Mummy", [(FAMILY, 3), (HINDI, 4)], 6); person(PINKY, "Pinky", fam, 10)
        person(SONU, "Sonu", fri, 3); person(DEEPAK, "Deepak Bhai", fri, 2)
        for nm, pools, wt in (("Mukesh Shift", wrk, 4), ("Salim Loader", wrk, 3), ("Harish Supervisor", wrk, 3), ("Rakesh", fri, 2),
                              ("Vinod Cab", [(GENERAL, 2)], 1), ("Bunty", fri, 2), ("Chhotu Dhaba", [(GENERAL, 1)], 1)):
            person(w.number(), nm, pools, wt)
        groups.append(("Shift B Loaders", [w.number() for _ in range(9)], [(WORK, 4), (GENERAL, 3), (FRIENDS, 1)], 8))
        groups.append(("Verma Family", [AJAY, MUMMY, PINKY] + [w.number() for _ in range(4)], [(FAMILY, 3), (FORWARDS, 2), (HINDI, 2)], 5))
        sms_ids = [("VM-SPHBNK", "bank", 5), ("JD-AIRTEL", "telco", 2), ("AX-FOODIE", "offer", 2), ("BZ-SHOPEE", "delivery", 2)]
        bank, acct = "Sapphire Bank", "XX2640"
    else:
        person(PRIYA, "Priya Office", wrk, 8); person(APPA, "Appa", [(FAMILY, 3), (ENGLISH, 2)], 5)
        person(AMMA, "Amma", [(FAMILY, 3), (ENGLISH, 1), (FORWARDS, 1)], 6); person(KARTHIK, "Karthik", fri, 4)
        for nm, pools, wt in (("Ravi CA Firm", wrk, 3), ("Swati Gym", fri, 2), ("Divya", fri, 3), ("Lakshmi Tailor", [(GENERAL, 1)], 1),
                              ("Nitin Accounts", wrk, 2), ("Farah", [(ENGLISH, 3), (FRIENDS, 1)], 2)):
            person(w.number(), nm, pools, wt)
        groups.append(("Accounts Team", [PRIYA] + [w.number() for _ in range(5)], [(WORK, 4), (ENGLISH, 2), (GENERAL, 1)], 7))
        groups.append(("Iyer Family", [APPA, AMMA, KARTHIK] + [w.number() for _ in range(3)], [(FAMILY, 2), (ENGLISH, 2), (FORWARDS, 2)], 5))
        sms_ids = [("AD-BUBANK", "bank", 5), ("JD-AIRTEL", "telco", 2), ("AX-FOODIE", "offer", 2), ("BZ-SHOPEE", "delivery", 2)]
        bank, acct = "Bharat Union Bank", "XX3851"

    network = {V, R, M, BHAI, SAMEER, SONU, DEEPAK, KIRTI}
    plain_names = [NAMES.get(n, nm) for n, nm, _, _ in people if n not in network]
    gkeys = []
    for name, members, pools, wt in groups:
        key = w.conv(f"whatsapp-group:{name.lower().replace(' ', '-')}-{p}", "whatsapp", [me] + members, {p: name}, True)
        gkeys.append((key, pools, wt))
    pkeys = []
    for number, name, pools, wt in people:
        key = w.conv(w.pair_key("whatsapp", me, number), "whatsapp", [me, number], {p: name})
        pkeys.append((key, number, pools, wt))
    tg = [w.conv(f"telegram-channel:{n.lower().replace(' ', '')}-{p}", "telegram", [me, "tg:" + n.lower().replace(" ", "")],
                 {p: n}, True) for n in ("Loot Deals Daily", "Cricket Live Updates")]
    merchants = ["SWIGGO FOODS", "QUICKMART", "METRO CARD RECHARGE", "FUEL POINT", "NAMMA KIRANA", "CITY PHARMACY",
                 "BOOKMYSEAT", "ELECTRIC BOARD", "SHOPEE ONLINE", "CAB RIDE"]
    tg_lines = ["Deal: earbuds at Rs 499 only", "Flash sale tonight 12 am", "Price drop on air fryers", "Coupon code SAVE20",
                "Score update: 145/3 after 18 overs", "Wicket! Big one", "Match starts 7:30 pm", "Rain delay at the ground"]

    target = TARGETS[p]
    remaining = target - len(w.events[p])
    kinds = ["message", "call", "location", "photo", "video", "voice", "document"]
    kw_ = [83, 10, 3, 1.6, 0.4, 1, 0.5]
    apps = [("whatsapp", 60), ("sms", 15), ("telegram", 4), ("signal", 2)] + ([("imessage", 2)] if p == 1 else [])
    gcount = {"img": 0}

    for _ in range(remaining):
        kind = rng.choices(kinds, weights=kw_)[0]
        if kind == "message":
            app = rng.choices([a for a, _ in apps], weights=[x for _, x in apps])[0]
            if app == "whatsapp":
                if rng.random() < 0.38:
                    key, pools, _w = rng.choices(gkeys, weights=[g[2] for g in gkeys])[0]
                    members = w.convs[key]["participants"]
                    sender = me if rng.random() < 0.2 else rng.choice(members[1:])
                else:
                    key, number, pools, _w = rng.choices(pkeys, weights=[x[3] for x in pkeys])[0]
                    sender = me if rng.random() < 0.5 else number
                t = w.when(False)
                body = w.line(pools, t)
                r = rng.random()
                st = "deleted" if r < 0.015 else ("unsent" if r < 0.018 else "")
                extra = {"note": "the sender unsent this message"} if st == "unsent" else None
                w.say(key, t, sender, "" if st == "unsent" else body, status={p: st}, extra=extra)
            elif app == "sms":
                t = w.when(False)
                if rng.random() < 0.8:
                    sid, kindsms, _x = rng.choices(sms_ids, weights=[s[2] for s in sms_ids])[0]
                    key = w.conv(f"sms:{me}|{sid}", "sms", [me, sid], {p: sid})
                    body = sms_body(rng, kindsms, bank, acct, t, merchants, plain_names)
                    w.say(key, t, sid, body)
                else:
                    key, number, pools, _w = rng.choice(pkeys)
                    skey = w.conv(w.pair_key("sms", me, number), "sms", [me, number], {p: w.convs[key]["titles"][p]})
                    w.say(skey, t, me if rng.random() < 0.5 else number, w.line(pools, t))
            elif app == "telegram":
                key = rng.choice(tg)
                w.say(key, w.when(False), w.convs[key]["participants"][1], rng.choice(tg_lines))
            elif app == "signal":
                key, number, pools, _w = rng.choice(pkeys[:4])
                skey = w.conv(w.pair_key("signal", me, number), "signal", [me, number], {p: w.convs[key]["titles"][p]})
                t = w.when(False)
                w.say(skey, t, me if rng.random() < 0.5 else number, w.line(pools, t))
            else:
                ikey = w.conv(w.pair_key("imessage", me, NEHA), "imessage", [me, NEHA], {p: "Neha"})
                t = w.when(False)
                w.say(ikey, t, me if rng.random() < 0.5 else NEHA, w.line([(FAMILY, 2), (ENGLISH, 2)], t))
        elif kind == "call":
            key, number, pools, _w = rng.choices(pkeys, weights=[x[3] for x in pkeys])[0]
            out = rng.random() < 0.5
            w.call([p], w.when(False), me if out else number, number if out else me,
                   rng.choice(["phone", "phone", "phone", "whatsapp"]), rng.randrange(8, 900), (not out) and rng.random() < 0.24)
        elif kind == "location":
            name, lat, lon, _wt = rng.choices(PLACES[p], weights=[x[3] for x in PLACES[p]])[0]
            w.add(p, kind="location", app="location", ts=w.when(False), lat=round(lat + rng.uniform(-0.0012, 0.0012), 6),
                  lon=round(lon + rng.uniform(-0.0012, 0.0012), 6), place=name, extra={"accuracy_m": rng.randrange(5, 40)})
        elif kind in ("photo", "video"):
            t = w.when(False)
            ocr = rng.choice([None, None, None, "Good Morning! Have a blessed day", "Hotel Annapurna | Bill Total Rs 1,240",
                              "Electricity bill | Amount due Rs 2,315", "Happy Diwali", "Menu | Thali Rs 180",
                              "Society notice: water supply off on Sunday"])
            if rng.random() < 0.5:
                key, number, pools, _w = rng.choices(pkeys, weights=[x[3] for x in pkeys])[0]
                w.say(key, t, me if rng.random() < 0.4 else number, "", kind=kind, media_size=rng.randrange(80_000, 3_500_000),
                      media_sha256=w.sha(), ocr_text=ocr if kind == "photo" else None,
                      duration_s=rng.randrange(5, 90) if kind == "video" else None)
            else:
                name, lat, lon, _wt = rng.choice(PLACES[p])
                w.add(p, kind=kind, app="camera", ts=t, direction="out", sender=me, lat=lat + rng.uniform(-0.001, 0.001),
                      lon=lon + rng.uniform(-0.001, 0.001), place=name, media_size=rng.randrange(900_000, 4_800_000),
                      media_sha256=w.sha(), ocr_text=ocr if kind == "photo" else None,
                      duration_s=rng.randrange(5, 120) if kind == "video" else None)
        elif kind == "voice":
            key, number, pools, _w = rng.choices(pkeys, weights=[x[3] for x in pkeys])[0]
            t = w.when(False)
            w.say(key, t, me if rng.random() < 0.4 else number, "", kind="voice", duration_s=rng.randrange(3, 60),
                  media_size=rng.randrange(5_000, 120_000), media_sha256=w.sha(),
                  transcript=w.line(pools, t) + ". " + rng.choice(GENERAL))
        else:
            doc = rng.choice([("Electricity_Bill_{m}.pdf", "Electricity bill | Account 1029384 | Amount due Rs 2,315"),
                              ("Rent_Receipt_{m}.pdf", "Rent receipt | Received Rs 28,000 for the month"),
                              ("Insurance_Policy.pdf", "Policy schedule | Health cover | Sum insured Rs 5,00,000"),
                              ("Duty_Roster_{m}.pdf", "Duty roster | Shift A 8 am - 8 pm | Shift B 8 pm - 8 am"),
                              ("Salary_Slip_{m}.pdf", "Salary slip | Net pay credited to bank"),
                              ("School_Fee_{m}.pdf", "Fee receipt | Term 2 | Paid")])
            t = w.when(False)
            mon = datetime.fromtimestamp(t / 1000, IST).strftime("%b%Y")
            w.add(p, kind="document", app="files", ts=t, direction="in", media_name=doc[0].format(m=mon),
                  media_size=rng.randrange(40_000, 900_000), media_sha256=w.sha(), ocr_text=doc[1])


def sms_body(rng, kind, bank, acct, t, merchants, names):
    d = datetime.fromtimestamp(t / 1000, IST).strftime("%d-%m-%y")
    ref = "6" + "".join(str(rng.randrange(10)) for _ in range(11))
    if kind == "bank":
        r = rng.random()
        amt = rng.choice([rng.randrange(100, 3000), rng.randrange(3000, 25000)])
        a = f"{amt:,}.00"
        if r < 0.55:
            return f"Rs {a} debited from A/c {acct} on {d} by UPI to {rng.choice(merchants)}. UPI Ref {ref}."
        if r < 0.75:
            return f"Rs {a} credited to A/c {acct} on {d} by UPI from {rng.choice(names).upper()}. Ref {ref}."
        if r < 0.9:
            return f"{rng.randrange(100000, 999999)} is your OTP for {bank} login. Do not share it with anyone."
        return f"Dear customer, your {bank} A/c {acct} balance is Rs {rng.randrange(2000, 180000):,}.{rng.randrange(10, 99)} as on {d}."
    if kind == "otp":
        return f"{rng.randrange(100000, 999999)} is your QuikPe verification code. Valid for 10 minutes."
    if kind == "telco":
        return rng.choice(["Your data pack is 90% used. Recharge now for uninterrupted service.",
                           "Bill of Rs 599 generated. Pay by the due date to avoid late fee.",
                           "Recharge successful. Validity 28 days. Enjoy unlimited calls."])
    if kind == "offer":
        return rng.choice(["Hungry? Flat 50% off on your next order. Use code YUM50", "Weekend special: free delivery on orders above Rs 199",
                           "Your order is out for delivery and will reach in 25 mins", "Rate your last meal and win cashback"])
    return rng.choice(["Your order has been shipped and will arrive tomorrow", "Parcel delivered. Thank you for shopping",
                       f"Your order {rng.randrange(10**7, 10**8)} is out for delivery", "Return pickup scheduled for tomorrow"])


# ---------------------------------------------------------------- write the exports

def _origin(p, ev, counters):
    k, app = ev["kind"], ev["app"]
    if p == 3:
        model = {"message": "Chat", "call": "Call", "location": "Location", "photo": "Picture", "video": "Video",
                 "voice": "Audio", "document": "Document"}[k]
        f, tab = "report.xml", f'<model type="{model}">'
    elif p == 1:
        f, tab = {
            ("whatsapp", "message"): ("ChatStorage.sqlite", "ZWAMESSAGE"), ("whatsapp", "photo"): ("ChatStorage.sqlite", "ZWAMEDIAITEM"),
            ("whatsapp", "video"): ("ChatStorage.sqlite", "ZWAMEDIAITEM"), ("whatsapp", "voice"): ("ChatStorage.sqlite", "ZWAMEDIAITEM"),
            ("sms", "message"): ("sms.db", "message"), ("imessage", "message"): ("sms.db", "message"),
            ("telegram", "message"): ("db_sqlite", "t7"), ("signal", "message"): ("signal.sqlite", "model_TSInteraction"),
        }.get((app, k), {"call": ("call_history.db", "ZCALLRECORD"), "location": ("Cache.sqlite", "ZRTCLLOCATIONMO"),
                         "photo": ("Photos.sqlite", "ZASSET"), "video": ("Photos.sqlite", "ZASSET"),
                         "document": ("Files.sqlite", "ZITEM")}.get(k, ("ChatStorage.sqlite", "ZWAMESSAGE")))
    else:
        f, tab = {
            ("whatsapp", "message"): ("msgstore.db", "message"), ("whatsapp", "photo"): ("msgstore.db", "message_media"),
            ("whatsapp", "video"): ("msgstore.db", "message_media"), ("whatsapp", "voice"): ("msgstore.db", "message_media"),
            ("whatsapp", "call"): ("msgstore.db", "call_log"), ("sms", "message"): ("mmssms.db", "sms"),
            ("telegram", "message"): ("cache4.db", "messages_v2"), ("signal", "message"): ("signal.db", "message"),
        }.get((app, k), {"call": ("calllog.db", "calls"), "location": ("gmm_myplaces.db", "sync_item"),
                         "photo": ("external.db", "files"), "video": ("external.db", "files"),
                         "document": ("external.db", "files")}.get(k, ("msgstore.db", "message")))
    key = (f, tab)
    counters[key] = counters.get(key, 1000 + 37 * len(counters)) + 1
    return {"file": f, "table": tab, "row": counters[key]}


def build() -> dict:
    """All three exports as dicts: {'phone1': {...}, 'phone2': {...}, 'phone3': {...}}."""
    w = World()
    plant(w)
    network_noise(w)
    for p in (1, 2, 3):
        private_noise(w, p)
    out = {}
    for p in (1, 2, 3):
        evs = sorted(w.events[p], key=lambda e: (e["ts"], e["_seq"]))
        counters, img = {}, 3000
        for e in evs:
            if e["kind"] in ("photo", "video") and not e.get("_named"):
                img += 1
                while img in (4398, 4471):
                    img += 1
                d = datetime.fromtimestamp(e["ts"] / 1000, IST)
                ext = "jpg" if e["kind"] == "photo" else "mp4"
                if p == 1:
                    e["media_name"] = f"IMG_{img}.{'JPG' if ext == 'jpg' else 'MOV'}"
                elif e["app"] == "whatsapp":
                    e["media_name"] = f"{'IMG' if ext == 'jpg' else 'VID'}-{d:%Y%m%d}-WA{img % 10000:04d}.{ext}"
                else:
                    e["media_name"] = f"{'IMG' if ext == 'jpg' else 'VID'}_{d:%Y%m%d_%H%M%S}.{ext}"
            if e["kind"] == "voice" and not e.get("media_name"):
                img += 1
                d = datetime.fromtimestamp(e["ts"] / 1000, IST)
                e["media_name"] = f"Audio_{d:%Y-%m-%d_%H%M%S}.opus" if p == 1 else f"PTT-{d:%Y%m%d}-WA{img % 10000:04d}.opus"
            e["origin"] = _origin(p, e, counters)
            if e["status"] == "deleted":
                e["extra"] = dict(e["extra"] or {}, recovered=True)
        events = []
        for e in evs:
            e = {k: v for k, v in e.items() if not k.startswith("_")}
            e["ts"] = iso(e["ts"])
            e["origin"] = e.pop("origin")
            events.append(e)
        used = []
        for e in events:
            if e["conv"] and e["conv"] not in used:
                used.append(e["conv"])
        convs = [{"key": k, "app": w.convs[k]["app"], "title": w.convs[k]["titles"][p], "is_group": w.convs[k]["is_group"],
                  "participants": w.convs[k]["participants"]} for k in used]
        contacts = [{"name": name, "numbers": [num]} for num, name in w.contacts[p].items()]
        out[f"phone{p}"] = {"format_version": GEN_VERSION, "device": APP_DEVICE[p], "owner": OWNERS[p],
                            "contacts": contacts, "conversations": convs, "events": events}
    return out


def _dumps(data) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _samples_dir(folder=None) -> Path:
    if folder is not None:
        return Path(folder)
    from ib import config
    return config.samples_dir()


def _current(path: Path) -> bool:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return f'"format_version":"{GEN_VERSION}"' in fh.read(200)
    except OSError:
        return False


def ensure_samples(folder=None, force: bool = False) -> list[Path]:
    """Write phone1.json, phone2.json and phone3.json if any is missing or from an older generator."""
    d = _samples_dir(folder)
    paths = [d / f"{n}.json" for n in SAMPLE_NAMES]
    if not force and all(_current(p) for p in paths):
        return paths
    d.mkdir(parents=True, exist_ok=True)
    data = build()
    for name, path in zip(SAMPLE_NAMES, paths):
        tmp = path.with_suffix(f".tmp{os.getpid()}")
        tmp.write_text(_dumps(data[name]), encoding="utf-8")
        os.replace(tmp, path)
    _cache.clear()
    return paths


def sample_path(name: str, folder=None) -> Path:
    if name not in SAMPLE_NAMES:
        raise ValueError("not a sample phone")
    ensure_samples(folder)
    return _samples_dir(folder) / f"{name}.json"


def load_sample(name: str, folder=None) -> dict:
    with open(sample_path(name, folder), "r", encoding="utf-8") as fh:
        return json.load(fh)


_cache: dict = {}


def samples(folder=None) -> list[dict]:
    """What /api/samples lists: one row per made-up phone, with device, owner and record count."""
    ensure_samples(folder)
    rows = []
    for i, name in enumerate(SAMPLE_NAMES, 1):
        path = _samples_dir(folder) / f"{name}.json"
        st = path.stat()
        ck = (str(path), st.st_mtime_ns, st.st_size)
        if ck not in _cache:
            data = load_sample(name, folder)
            dev = data["device"]
            kind_word = {"iphone-backup": "iPhone", "android-backup": "Android", "ufdr-report": "Android"}[dev["platform"]]
            _cache[ck] = {
                "id": name, "sample": name, "phone_no": i, "label": f"Phone {i} | {dev['label_owner']}'s {kind_word}",
                "owner": data["owner"]["name"], "number": dev["sims"][0]["number"], "device": dev["model"], "os": dev["os"],
                "platform": dev["platform"], "file_name": dev["file_name"], "records": len(data["events"]),
                "contacts": len(data["contacts"]), "chats": len(data["conversations"]),
                "first": data["events"][0]["ts"], "last": data["events"][-1]["ts"], "size_bytes": st.st_size,
            }
        rows.append(dict(_cache[ck]))
    return rows


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    for path in ensure_samples(target, force=True):
        print(path)
    for row in samples(target):
        print(row["label"], row["records"], "records")

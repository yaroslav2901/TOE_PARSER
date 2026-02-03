import urllib.request
import ssl
from datetime import datetime, timedelta
import json
import os
import time
import base64

LOG_FILE = os.path.join(os.path.dirname(__file__), '../logs/cron.log')


class ToeOutageParser:
    BASE_URL = "https://api-toe-poweron.inneti.net/api"

    STATUS_MAP = {
        "0": "yes",      # Світло є
        "1": "no",       # Відключення
        "10": "no",      # Можливе відключення
    }

    # Кожна група зовяязана з cityId і streetId
    # Один запрос a_gpv_g з x-debug-key=base64(cityId/streetId) вертає
    # всі групи на цій вулиці
    # Групуємо по (cityId, streetId) щоб робити мінімум запросів
    GROUP_KEYS = {
        # (cityId, streetId): [list of groups on this street]
        (514,   31361): ['6.1'],
        (604,   6050):  ['2.1'],
        (919,   8835):  ['1.1'],
        (1032,  9982):  ['4.1', '5.1'],
        (1032,  9996):  ['3.2', '4.2'],
        (1032,  9999):  ['1.2', '2.2'],
        (1032,  10021): ['5.2'],
        (21346, 35118): ['3.1'],
        (21547, 36889): ['6.2'],
    }

    @staticmethod
    def build_debug_key(city_id: int, street_id: int) -> str:
        return base64.b64encode(f"{city_id}/{street_id}".encode()).decode()

    @staticmethod
    def fetch_all_groups(before: str, after: str):
        """Один цикл по всіх known keys — вертає dict {group_name: {dateGraph, intervals}}"""
        results = {}
        now_ts = int(time.time() * 1000)

        for i, ((city_id, street_id), expected_groups) in enumerate(ToeOutageParser.GROUP_KEYS.items()):
            key = ToeOutageParser.build_debug_key(city_id, street_id)
            tp = f"{now_ts + i}%D0%B0"
            query = f"before={before.replace('+', '%2B')}&after={after.replace('+', '%2B')}&group[]={expected_groups[0]}&time={tp}"
            url = f"{ToeOutageParser.BASE_URL}/a_gpv_g?{query}"

            headers = {
                'Accept': 'application/json, text/plain, */*',
                'Origin': 'https://toe-poweron.inneti.net',
                'Referer': 'https://toe-poweron.inneti.net/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36',
                'X-debug-key': key,
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-site',
            }

            try:
                data = ToeOutageParser.fetch_json(url, headers)
                members = data.get("hydra:member", []) if isinstance(data, dict) else data

                for member in members:
                    date_graph = member.get("dateGraph", "unknown")
                    data_json = member.get("dataJson", {})
                    for group_name, group_data in data_json.items():
                        times = group_data.get("times", {})
                        intervals = ToeOutageParser.parse_outage_intervals_from_times(times)
                        results[group_name] = {
                            "dateGraph": date_graph,
                            "intervals": intervals,
                        }
            except Exception as e:
                print(f"  Error for {city_id}/{street_id}: {e}")
                continue

        return results

    @staticmethod
    def parse_outage_intervals_from_times(times: dict):
        half_hours = ["yes"] * 48

        for time_str, value in times.items():
            idx = ToeOutageParser.time_to_half_hour_index(time_str)
            if idx is None:
                continue
            half_hours[idx] = "no" if ToeOutageParser.is_outage_value(value) else "yes"

        return ToeOutageParser.build_intervals_from_half_hours(half_hours)

    @staticmethod
    def is_outage_value(value):
        return str(value) in ("1", "10")

    @staticmethod
    def build_intervals_from_half_hours(half_hours):
        intervals = []
        in_outage = False
        start_idx = 0
        count = len(half_hours)

        for i in range(count + 1):
            status = half_hours[i] if i < count else "yes"

            if not in_outage and status == "no":
                in_outage = True
                start_idx = i

            if in_outage and status != "no":
                intervals.append(f"{ToeOutageParser.format_half_hour_time(start_idx)} - "
                                 f"{ToeOutageParser.format_half_hour_time(i)}")
                in_outage = False

        return intervals

    @staticmethod
    def time_to_half_hour_index(time_str: str):
        try:
            h, m = map(int, time_str.split(":"))
            if h < 0 or h > 23 or m not in (0, 30):
                return None
            return h * 2 + (1 if m == 30 else 0)
        except ValueError:
            return None

    @staticmethod
    def format_half_hour_time(idx: int):
        h = idx // 2
        m = 30 if idx % 2 else 0
        return f"{h:02d}:{m:02d}"

    @staticmethod
    def fetch_json(url, headers):
        try:
            req = urllib.request.Request(url, headers=headers)
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                http_code = resp.status
                content_type = resp.headers.get("Content-Type", "")
                body = resp.read().decode("utf-8")
                data = json.loads(body)
                ToeOutageParser.log_request(url, headers, http_code, content_type, body)
                return data
        except urllib.error.HTTPError as e:
            ToeOutageParser.log_request(url, headers, e.code, "", f"ERROR: {e.reason}")
            raise
        except Exception as e:
            ToeOutageParser.log_request(url, headers, 0, "", f"ERROR: {str(e)}")
            raise

    @staticmethod
    def log_request(url, headers, http_code, content_type, body):
        lines = [
            "--- {} ---".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            f"URL: {url}",
            f"Headers: {headers}",
            f"HTTP: {http_code}",
            f"Content-Type: {content_type}",
            f"Body: {body}",
            ""
        ]
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


# ================= TEST =================
if __name__ == "__main__":
    now = datetime.utcnow()
    before = (now + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00+00:00")
    after = (now - timedelta(days=1)).strftime("%Y-%m-%dT12:00:00+00:00")

    print("Запрошуємо графіки...\n")
    results = ToeOutageParser.fetch_all_groups(before, after)

    # Виводимо в порядку груп
    all_groups = sorted(results.keys())
    for g in all_groups:
        info = results[g]
        print(f"Група {g} ({info['dateGraph']}):")
        if info["intervals"]:
            for interval in info["intervals"]:
                print(f"  ❌ {interval}")
        else:
            print("  ✅ Відключень немає")
        print()

    if not results:
        print("Нічого не отримано")
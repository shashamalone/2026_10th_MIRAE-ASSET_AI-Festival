import json

with open("lseg_static_metadata.json", encoding="utf-8") as f:
    data = json.load(f)

themes = sorted({theme for item in data.values() for theme in item.get("themes", [])})

with open("theme_list.json", "w", encoding="utf-8") as f:
    json.dump(themes, f, ensure_ascii=False, indent=2)

print(len(themes), "개 테마 추출 완료 -> theme_list.json")

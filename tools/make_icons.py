# -*- coding: utf-8 -*-
"""app/assets/icons/*.svg 생성기 (직접 그린 단색 라인 아이콘)
규격: 24x24, stroke 1.75, round cap/join, fill none, 색은 currentColor → 앱에서 테마 색으로 치환
실행: .venv\\Scripts\\python.exe tools\\make_icons.py
"""
import os

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "assets", "icons")

PAGE = "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z M14 3v5h5"
MAG = '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5 5"/>'

ICONS = {
    # 파일
    "open": '<path d="M3 18V6.5A1.5 1.5 0 0 1 4.5 5H9l2 2.5h7.5A1.5 1.5 0 0 1 20 9v1.5"/>'
            '<path d="M3 18l2.6-6.4A1.5 1.5 0 0 1 7 10.5h13.2a1 1 0 0 1 .9 1.4L18.6 18a1.5 1.5 0 0 1-1.4 1H4.5A1.5 1.5 0 0 1 3 17.5"/>',
    "merge": '<rect x="8" y="3" width="12" height="14" rx="2"/><path d="M4 7.5V19a2 2 0 0 0 2 2h10"/>'
             '<path d="M14 7v6M11 10h6"/>',
    "save": '<path d="M5 5a1 1 0 0 1 1-1h10l3 3v12a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1z"/><path d="M8 4v4.5h7V4"/>'
            '<rect x="8" y="13" width="8" height="7" rx="1"/>',
    "save-as": f'<path d="{PAGE}"/><path d="M12 11v6M9 14.5l3 3 3-3"/>',
    "undo": '<path d="M9 6L5 10l4 4"/><path d="M5 10h9.5a4.5 4.5 0 0 1 0 9H11"/>',
    "redo": '<path d="M15 6l4 4-4 4"/><path d="M19 10H9.5a4.5 4.5 0 0 0 0 9H13"/>',
    # 페이지
    "rotate-left": '<path d="M4.5 13A7.5 7.5 0 1 0 7 6.6"/><path d="M4 3.5V8h4.5"/>',
    "rotate-right": '<path d="M19.5 13A7.5 7.5 0 1 1 17 6.6"/><path d="M20 3.5V8h-4.5"/>',
    "trash": '<path d="M4 7h16M9.5 7V4.5h5V7"/><path d="M6.5 7l.8 12a1.5 1.5 0 0 0 1.5 1.4h6.4a1.5 1.5 0 0 0 1.5-1.4l.8-12"/>'
             '<path d="M10 11v5.5M14 11v5.5"/>',
    "page-add": f'<path d="{PAGE}"/><path d="M12 11v6M9 14h6"/>',
    "arrow-up": '<path d="M12 19V5M6.5 10.5L12 5l5.5 5.5"/>',
    "arrow-down": '<path d="M12 5v14M6.5 13.5L12 19l5.5-5.5"/>',
    "extract": '<path d="M13 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-2.5"/><path d="M13 3l4 4v2"/>'
               '<path d="M11 13h10M18 10l3 3-3 3"/>',
    "split": '<circle cx="6.5" cy="7" r="2.5"/><circle cx="6.5" cy="17" r="2.5"/>'
             '<path d="M8.6 8.4L20 17.5M8.6 15.6L20 6.5"/>',
    # 편집
    "text-add": '<path d="M4 6.5V4.5h12v2M10 4.5V19M7.5 19h5"/><path d="M18 13v6M15 16h6"/>',
    "text-edit": '<path d="M4 6.5V4.5h11v2M9.5 4.5V15"/><path d="M12 20l1-3.5 6-6 2.5 2.5-6 6z"/>',
    "eraser": '<path d="M9 20h11"/><path d="M5 15.5l8.6-8.6a1.8 1.8 0 0 1 2.5 0l2.5 2.5a1.8 1.8 0 0 1 0 2.5L12 18.5H8z"/>'
              '<path d="M9.5 11l5 5"/>',
    "insert-image": '<rect x="3" y="5" width="13" height="12" rx="2"/><circle cx="7.5" cy="9.5" r="1.25"/>'
                    '<path d="M16 14l-3.5-3.5L5 17"/><path d="M19.5 13.5v7M16 17h7"/>',
    "signature": '<path d="M3 16.5c2.2 0 3.3-9 5.8-9 2 0 .2 8.5 2.7 8.5 1.6 0 2.1-3 3.5-3 1.2 0 1.2 2 2.5 2 1 0 1.6-.8 2.5-.8"/>'
                 '<path d="M3 20.5h18"/>',
    "stamp": '<path d="M9.5 4h5v3.5c0 1.5-1.5 2.2-1.5 4h-2c0-1.8-1.5-2.5-1.5-4z"/><path d="M5 14.5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v2H5z"/>'
             '<path d="M6 20h12"/>',
    "info": '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5"/><path d="M12 7.6v.1"/>',
    "scroll-view":'<rect x="6" y="2.5" width="12" height="8" rx="1.5"/><rect x="6" y="13.5" width="12" height="8" rx="1.5"/>'
                   '<path d="M21 7v10M19.5 15.5L21 17l1.5-1.5"/>',
    "compress":'<path d="M12 3v6M9 6l3 3 3-3"/><path d="M12 21v-6M9 18l3-3 3 3"/><path d="M4 12h16"/>',
    "page-deco":f'<path d="{PAGE}"/><path d="M9.5 18h5"/><path d="M8.5 13.5l7-4"/>',
    "annotate":'<path d="M14.5 4l5.5 5.5-8.5 8.5H6v-5.5z"/><path d="M11.5 7l5.5 5.5"/><path d="M3.5 21h10"/>',
    "underline": '<path d="M7 4v7a5 5 0 0 0 10 0V4"/><path d="M5 20.5h14"/>',
    "shape-rect": '<rect x="4" y="6" width="16" height="12" rx="1.5"/>',
    "shape-arrow": '<path d="M5 19L18.5 5.5"/><path d="M10 5h9v9"/>',
    "note": '<path d="M5 4.5h14a1 1 0 0 1 1 1V15l-5 5H5a1 1 0 0 1-1-1V5.5a1 1 0 0 1 1-1z"/>'
            '<path d="M15 20v-4a1 1 0 0 1 1-1h4"/><path d="M8 9h8M8 12.5h5"/>',
    "replace": '<path d="M4 8h11.5M12.5 4.5L16 8l-3.5 3.5"/><path d="M20 16H8.5M11.5 12.5L8 16l3.5 3.5"/>',
    "search": MAG,
    "color": '<path d="M12 3.5c3 3.4 6 6.8 6 10.3a6 6 0 0 1-12 0c0-3.5 3-6.9 6-10.3z"/>',
    "more": '<circle cx="5.5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="18.5" cy="12" r="1"/>',
    # 보기
    "zoom-in": MAG + '<path d="M10.5 8v5M8 10.5h5"/>',
    "zoom-out": MAG + '<path d="M8 10.5h5"/>',
    "fit-width": '<path d="M4 5v14M20 5v14"/><path d="M7.5 12h9M10 9.5L7.5 12l2.5 2.5M14 9.5l2.5 2.5-2.5 2.5"/>',
    # 내비게이션
    "nav-pdf": f'<path d="{PAGE}"/><path d="M9 12.5h6M9 16h4"/>',
    "nav-image": '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><circle cx="9" cy="9.5" r="1.5"/>'
                 '<path d="M20.5 15.5l-4.5-4.5-8.5 8.5"/>',
    "nav-convert": '<path d="M4 8h13M13.5 4.5L17 8l-3.5 3.5"/><path d="M20 16H7M10.5 12.5L7 16l3.5 3.5"/>',
    "moon": '<path d="M19.5 14.5A7.5 7.5 0 1 1 9.5 4.5a6 6 0 0 0 10 10z"/>',
    "sun": '<circle cx="12" cy="12" r="3.75"/><path d="M12 3v1.5M12 19.5V21M3 12h1.5M19.5 12H21'
           'M5.6 5.6l1.1 1.1M17.3 17.3l1.1 1.1M5.6 18.4l1.1-1.1M17.3 6.7l1.1-1.1"/>',
    # 공통
    "upload": '<path d="M12 15V4.5M7.5 9L12 4.5 16.5 9"/><path d="M4 14.5V18a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3.5"/>',
    "folder-add": '<path d="M3 17.5v-11A1.5 1.5 0 0 1 4.5 5H9l2 2.5h8.5A1.5 1.5 0 0 1 21 9v8.5a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5z"/>'
                  '<path d="M12 10.5v5M9.5 13h5"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "minus": '<path d="M5 12h14"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "sort": '<path d="M7 4.5v15M4 16.5l3 3 3-3"/><path d="M13 6h7M13 10.5h5M13 15h3"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21'
                'M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M5.6 18.4l1.8-1.8M16.6 7.4l1.8-1.8"/>',
    "play": '<path d="M7 5l11 7-11 7z"/>',
    # 변환 카드
    "conv-pdf-img": f'<path d="{PAGE}"/><circle cx="9.5" cy="12" r="1.25"/><path d="M19 17l-3.5-3.5L8 21"/>',
    "conv-img-pdf": '<rect x="3.5" y="4.5" width="11" height="10" rx="1.5"/><path d="M14.5 12l-3-3-6 5.5"/>'
                    '<path d="M17 10h1.5a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-8a2 2 0 0 1-2-2v-1.5"/>',
    "conv-office-pdf": '<rect x="3.5" y="3.5" width="17" height="17" rx="2"/><path d="M3.5 9h17M3.5 14.5h17M9.5 9v11.5"/>',
    "conv-pdf-doc": f'<path d="{PAGE}"/><path d="M8.5 12h7M8.5 15h7M8.5 18h4"/>',
}


def svg(body):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" '
            'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
            + body.replace('d="', 'd="') + '</svg>\n')


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, body in ICONS.items():
        if body.lstrip().startswith('<'):
            content = body
        else:
            content = f'<path d="{body}"/>'
        with open(os.path.join(OUT, name + ".svg"), "w", encoding="utf-8", newline="\n") as f:
            f.write(svg(content))
    print(f"{len(ICONS)} icons -> {OUT}")


if __name__ == "__main__":
    main()

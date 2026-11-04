"""Conservative orientation aid for sideways ruled answer sheets, independent of exam content."""
from pathlib import Path


def sideways_ruled_page(path: Path) -> bool:
    import cv2
    import numpy as np
    image = cv2.imread(str(path))
    if image is None:
        return False
    height, width = image.shape[:2]
    scale = min(1, 1000 / max(height, width))
    image = cv2.resize(image, None, fx=scale, fy=scale)
    height, width = image.shape[:2]
    edges = cv2.Canny(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 100,
                            minLineLength=min(height, width) * .45, maxLineGap=30)
    if lines is None:
        return False
    vertical, horizontal, columns = 0, 0, set()
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        dx, dy = abs(x2 - x1), abs(y2 - y1)
        if dx < dy * .08:
            vertical += 1
            columns.add(round(((int(x1) + int(x2)) / 2) / max(1, width / 40)))
        if dy < dx * .08:
            horizontal += 1
    # Require many widely distributed long lines, not a margin or a narrow table.
    return vertical >= 12 and len(columns) >= 10 and vertical > 4 * max(1, horizontal)

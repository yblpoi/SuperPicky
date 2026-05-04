#!/usr/bin/env python3
"""
AvonetFilter - 基于 avonet.db 的离线物种过滤器

使用 AVONET 全球鸟类分布数据进行离线物种过滤，
替代需要网络连接的 eBird API。

数据库结构：
- distributions: 物种-网格映射 (species, worldid)
- places: 1x1 度网格边界 (worldid, south, north, west, east)
- sp_cls_map: 物种名 -> OSEA class_id 映射 (species, cls)
"""

import os
import sqlite3
from typing import Set, List, Optional, Tuple
from config import get_install_scoped_resource_path
from tools.i18n import t as _t

REGION_BOUNDS = {
    "GLOBAL": (-90, 90, -180, 180),
    "AF": (-35, 37, -17, 51),
    "AS": (-10, 81, 26, 170),
    "EU": (34, 71, -25, 45),
    "NA": (14, 83, -168, -52),
    "SA": (-56, 13, -81, -34),
    "OC": (-47, -10, 110, 180),
    "AU": (-44, -10, 112, 155),
    "NZ": (-47.5, -34, 166, 179),
    "CN": (18, 54, 73, 135),
    "JP": (24, 46, 122, 154),
    "KR": (33, 43, 124, 132),
    "TW": (21.5, 25.5, 119, 122.5),
    "HK": (22.1, 22.6, 113.8, 114.5),
    "TH": (5.5, 20.5, 97.5, 105.5),
    "MY": (0.5, 7.5, 99.5, 119.5),
    "SG": (1.1, 1.5, 103.6, 104.1),
    "ID": (-11, 6, 95, 141),
    "PH": (4.5, 21, 116, 127),
    "VN": (8, 23.5, 102, 110),
    "IN": (6, 36, 68, 98),
    "LK": (5, 10, 79, 82),
    "NP": (26, 31, 80, 88),
    "MN": (41, 52, 87, 120),
    "RU": (41, 82, 19, 180),
    "US": (24, 49, -125, -66),
    "CA": (42, 83, -141, -52),
    "MX": (14, 33, -118, -86),
    "BR": (-34, 5.5, -74, -34),
    "AR": (-55, -21, -73, -53),
    "CL": (-56, -17, -76, -66),
    "CO": (-4.5, 13, -79, -66),
    "PE": (-18.5, 0, -81, -68),
    "EC": (-5, 2, -81, -75),
    "CR": (8, 11.5, -86, -82.5),
    "GB": (49, 61, -8, 2),
    "FR": (41, 51.5, -5, 10),
    "DE": (47, 55.5, 5.5, 15.5),
    "ES": (35.5, 44, -10, 4.5),
    "IT": (36, 47.5, 6.5, 18.5),
    "NO": (57.5, 71.5, 4.5, 31.5),
    "SE": (55, 69.5, 10.5, 24.5),
    "FI": (59.5, 70.5, 19.5, 31.5),
    "PL": (49, 55, 14, 24.5),
    "TR": (35.5, 42.5, 25.5, 45),
    "PT": (36, 42, -10, -6),
    "NL": (50, 54, 3, 8),
    "CH": (45, 48, 5, 11),
    "GR": (34, 42, 19, 29),
    "UA": (44, 53, 22, 41),
    "MG": (-26, -11, 43, 51),
    "ZA": (-35, -22, 16.5, 33),
    "KE": (-5, 5, 33.5, 42),
    "TZ": (-12, -1, 29, 41),
    "EG": (22, 32, 24.5, 37),
    "MA": (27, 36, -13, -1),
    "AU-QLD": (-29, -10, 138, 154),
    "AU-NSW": (-37.5, -28, 141, 154),
    "AU-VIC": (-39.2, -34, 141, 150),
    "AU-TAS": (-43.7, -39.5, 143.5, 148.5),
    "AU-SA": (-38, -26, 129, 141),
    "AU-WA": (-35, -13.5, 112.5, 129),
    "AU-NT": (-26, -10.5, 129, 138),
    "AU-ACT": (-35.95, -35.1, 148.75, 149.4),
    "US-AL": (30, 35, -88.5, -84.9),
    "US-AK": (51, 72, -168, -130),
    "US-AZ": (31.3, 37, -114.8, -109),
    "US-AR": (33, 36.5, -94.6, -89.6),
    "US-CA": (32.5, 42, -124.5, -114),
    "US-CO": (37, 41, -109, -102),
    "US-CT": (40.9, 42.1, -73.7, -71.8),
    "US-DE": (38.4, 39.8, -75.8, -75),
    "US-FL": (24.4, 31, -87.7, -80),
    "US-GA": (30.4, 35, -85.6, -80.8),
    "US-HI": (18.9, 22.2, -160.3, -154.8),
    "US-ID": (42, 49, -117.2, -111),
    "US-IL": (36.9, 42.5, -91.5, -87.5),
    "US-IN": (37.8, 41.8, -88.1, -84.8),
    "US-IA": (40.4, 43.5, -96.6, -90.1),
    "US-KS": (37, 40, -102.1, -94.6),
    "US-KY": (36.5, 39.2, -89.6, -81.9),
    "US-LA": (28.9, 33.1, -94.1, -88.8),
    "US-ME": (43.1, 47.5, -71.1, -66.9),
    "US-MD": (37.9, 39.7, -79.5, -75),
    "US-MA": (41.2, 42.9, -73.5, -69.9),
    "US-MI": (41.7, 48.3, -90.4, -82.4),
    "US-MN": (43.5, 49.4, -97.2, -89.5),
    "US-MS": (30, 35, -91.7, -88.1),
    "US-MO": (36, 40.6, -95.8, -89.1),
    "US-MT": (44.4, 49, -116.1, -104),
    "US-NE": (40, 43, -104.1, -95.3),
    "US-NV": (35, 42, -120, -114),
    "US-NH": (42.7, 45.3, -72.6, -70.7),
    "US-NJ": (38.9, 41.4, -75.6, -73.9),
    "US-NM": (31.3, 37, -109.1, -103),
    "US-NY": (40.5, 45.1, -79.8, -71.9),
    "US-NC": (33.8, 36.6, -84.3, -75.5),
    "US-ND": (45.9, 49, -104.1, -96.6),
    "US-OH": (38.4, 42, -84.8, -80.5),
    "US-OK": (33.6, 37, -103, -94.4),
    "US-OR": (41.9, 46.3, -124.6, -116.5),
    "US-PA": (39.7, 42.3, -80.5, -74.7),
    "US-RI": (41.1, 42.1, -71.9, -71.1),
    "US-SC": (32, 35.2, -83.4, -78.5),
    "US-SD": (42.5, 45.9, -104.1, -96.4),
    "US-TN": (35, 36.7, -90.3, -81.6),
    "US-TX": (25.8, 36.5, -106.6, -93.5),
    "US-UT": (37, 42, -114.1, -109),
    "US-VT": (42.7, 45.1, -73.4, -71.5),
    "US-VA": (36.5, 39.5, -83.7, -75.2),
    "US-WA": (45.5, 49, -124.8, -116.9),
    "US-WV": (37.2, 40.6, -82.7, -77.7),
    "US-WI": (42.5, 47.1, -92.9, -86.8),
    "US-WY": (41, 45, -111.1, -104),
    "CN-11": (39.4, 41.1, 115.4, 117.7),
    "CN-12": (38.6, 40.3, 116.7, 118.1),
    "CN-13": (36, 42.7, 113.5, 119.8),
    "CN-14": (34.6, 40.7, 110.2, 114.6),
    "CN-15": (37.5, 53.3, 97.2, 126.1),
    "CN-21": (38.7, 43.5, 118.8, 125.7),
    "CN-22": (41.2, 46, 121.6, 131.3),
    "CN-23": (43.4, 53.6, 121.1, 135.1),
    "CN-31": (30.7, 31.9, 120.8, 122),
    "CN-32": (30.8, 35.1, 116.4, 121.9),
    "CN-33": (27.1, 31.2, 118.1, 122.9),
    "CN-34": (29.4, 34.7, 114.9, 119.9),
    "CN-35": (23.5, 28.3, 115.8, 120.7),
    "CN-36": (24.5, 30.1, 113.6, 118.5),
    "CN-37": (34.4, 38.3, 114.8, 122.7),
    "CN-41": (31.4, 36.4, 110.4, 116.7),
    "CN-42": (29.1, 33.2, 108.4, 116.1),
    "CN-43": (24.6, 30.1, 108.8, 114.3),
    "CN-44": (20.2, 25.5, 109.7, 117.3),
    "CN-45": (20.9, 26.4, 104.5, 112.1),
    "CN-46": (18.1, 20.2, 108.4, 111.2),
    "CN-50": (28.2, 32.2, 105.3, 110.2),
    "CN-51": (26, 34.3, 97.4, 108.5),
    "CN-52": (24.6, 29.2, 103.6, 109.6),
    "CN-53": (21.1, 29.3, 97.5, 106.2),
    "CN-54": (26.8, 36.5, 78.4, 99.1),
    "CN-61": (31.7, 39.6, 105.5, 111.3),
    "CN-62": (32.6, 42.8, 92.4, 108.7),
    "CN-63": (31.6, 39.2, 89.4, 103.1),
    "CN-64": (35.2, 39.4, 104.3, 107.7),
    "CN-65": (34.3, 49.2, 73.5, 96.4),
}


class AvonetFilter:
    """
    基于 AVONET 数据库的离线物种过滤器

    使用 1x1 度网格的鸟类分布数据，支持：
    - GPS 坐标查询：返回该位置可能出现的物种
    - 区域代码查询：返回指定区域的物种列表
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        初始化 AvonetFilter

        Args:
            db_path: avonet.db 的路径，如果为 None 则自动定位
        """
        if db_path is None:
            db_path = self._find_database()

        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._ebird_cls_map: Optional[dict] = None

        if self.db_path and os.path.exists(self.db_path):
            try:
                self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
                self._conn.row_factory = sqlite3.Row
            except sqlite3.Error as e:
                print(_t("logs.avonet_db_failed", e=e))
                self._conn = None

    def _find_database(self) -> Optional[str]:
        """
        自动查找 avonet.db 文件

        查找顺序：
        1. 统一安装目录资源路径
        2. 兼容旧开发目录
        """
        possible_paths = [
            str(get_install_scoped_resource_path(os.path.join("birdid", "data", "avonet.db"))),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "avonet.db"),
        ]

        for path in possible_paths:
            abs_path = os.path.abspath(path)
            if os.path.exists(abs_path):
                return abs_path

        return None

    def is_available(self) -> bool:
        """
        检查数据库是否可用

        Returns:
            True 如果数据库连接正常且包含数据
        """
        if self._conn is None:
            return False

        try:
            cursor = self._conn.execute("SELECT COUNT(*) FROM sp_cls_map")
            count = cursor.fetchone()[0]
            return count > 0
        except sqlite3.Error:
            return False

    def get_species_by_gps(self, lat: float, lon: float) -> Set[int]:
        """
        根据 GPS 坐标获取该位置可能出现的物种 class_ids

        使用 1x1 度网格查询，返回所有在该网格中有分布记录的物种。

        Args:
            lat: 纬度 (-90 到 90)
            lon: 经度 (-180 到 180)

        Returns:
            物种 class_id 的集合，如果查询失败返回空集合
        """
        if self._conn is None:
            return set()

        try:
            query = """
                SELECT DISTINCT sm.cls
                FROM distributions d
                JOIN places p ON d.worldid = p.worldid
                JOIN sp_cls_map sm ON d.species = sm.species
                WHERE ? BETWEEN p.south AND p.north
                  AND ? BETWEEN p.west AND p.east
            """
            cursor = self._conn.execute(query, (lat, lon))
            return {row[0] for row in cursor.fetchall()}
        except sqlite3.Error as e:
            print(_t("logs.avonet_gps_failed", e=e))
            return set()

    def get_species_by_region(self, region_code: str) -> Set[int]:
        """
        根据区域代码获取该区域的物种 class_ids

        Args:
            region_code: 区域代码 (如 "AU", "AU-SA", "CN", "JP")

        Returns:
            物种 class_id 的集合，如果区域不支持返回空集合
        """
        region_code = region_code.upper()

        if region_code not in REGION_BOUNDS:
            print(_t("logs.avonet_unsupported_region", code=region_code))
            return set()

        bounds = REGION_BOUNDS[region_code]
        return self._get_species_by_bounds(*bounds)

    def _get_species_by_bounds(
        self, south: float, north: float, west: float, east: float
    ) -> Set[int]:
        """
        根据边界框查询物种 class_ids

        查询所有与边界框有重叠的网格中的物种。

        Args:
            south: 南边界纬度
            north: 北边界纬度
            west: 西边界经度
            east: 东边界经度

        Returns:
            物种 class_id 的集合
        """
        if self._conn is None:
            return set()

        try:
            query = """
                SELECT DISTINCT sm.cls
                FROM distributions d
                JOIN places p ON d.worldid = p.worldid
                JOIN sp_cls_map sm ON d.species = sm.species
                WHERE p.north >= ? AND p.south <= ?
                  AND p.east >= ? AND p.west <= ?
            """
            cursor = self._conn.execute(query, (south, north, west, east))
            return {row[0] for row in cursor.fetchall()}
        except sqlite3.Error as e:
            print(_t("logs.avonet_bbox_failed", e=e))
            return set()

    def get_supported_regions(self) -> List[str]:
        """
        获取支持的区域代码列表

        Returns:
            支持的区域代码列表，按字母顺序排序
        """
        return sorted(REGION_BOUNDS.keys())

    def get_region_bounds(self, region_code: str) -> Optional[Tuple[float, float, float, float]]:
        """
        获取区域的边界坐标

        Args:
            region_code: 区域代码

        Returns:
            (south, north, west, east) 元组，如果区域不存在返回 None
        """
        return REGION_BOUNDS.get(region_code.upper())

    def close(self) -> None:
        """关闭数据库连接"""
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
            finally:
                self._conn = None

    def __enter__(self):
        """支持 context manager 协议"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出时关闭连接"""
        self.close()
        return False

    def __del__(self):
        """析构时关闭连接"""
        self.close()

    def _load_ebird_cls_map(self) -> dict:
        """懒加载 ebird_classid_mapping.json，返回 ebird_code -> class_id 的反向映射"""
        if self._ebird_cls_map is not None:
            return self._ebird_cls_map

        module_dir = os.path.dirname(os.path.abspath(__file__))
        map_path = os.path.join(module_dir, "data", "ebird_classid_mapping.json")
        if not os.path.exists(map_path):
            self._ebird_cls_map = {}
            return self._ebird_cls_map

        try:
            import json
            with open(map_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self._ebird_cls_map = {v: int(k) for k, v in raw.items()}
        except Exception as e:
            print(_t("logs.avonet_classid_failed", e=e))
            self._ebird_cls_map = {}

        return self._ebird_cls_map

    def _detect_country_from_gps(self, lat: float, lon: float) -> Optional[str]:
        """
        根据 GPS 坐标离线判定国家代码（仅返回国家级，不含州级）。
        优先匹配面积最小的边界框，避免大国遮蔽小国。
        """
        _SKIP = {"GLOBAL", "AF", "AS", "EU", "NA", "SA", "OC"}

        candidates = []
        for code, bounds in REGION_BOUNDS.items():
            if code in _SKIP:
                continue
            south, north, west, east = bounds
            if south <= lat <= north and west <= lon <= east:
                area = (north - south) * (east - west)
                candidates.append((area, code))

        if not candidates:
            return None

        candidates.sort()
        return candidates[0][1]

    def get_species_by_country_ebird(
        self, lat: float, lon: float
    ) -> Tuple[Set[int], Optional[str]]:
        """
        根据 GPS 坐标判定国家，加载 eBird 离线物种列表，返回 class_id 集合。

        Args:
            lat: 纬度
            lon: 经度

        Returns:
            (class_id_set, country_code) 或 (set(), None)
        """
        country_code = self._detect_country_from_gps(lat, lon)
        if not country_code:
            return set(), None

        module_dir = os.path.dirname(os.path.abspath(__file__))
        species_file = os.path.join(
            module_dir, "data", "offline_ebird_data",
            f"species_list_{country_code}.json"
        )
        if not os.path.exists(species_file):
            print(_t("logs.avonet_no_ebird_data", code=country_code))
            return set(), None

        try:
            import json
            with open(species_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            ebird_codes: List[str] = data.get("species", [])
        except Exception as e:
            print(_t("logs.avonet_read_ebird_failed", code=country_code, e=e))
            return set(), None

        cls_map = self._load_ebird_cls_map()
        class_ids: Set[int] = set()
        for code in ebird_codes:
            cls_id = cls_map.get(code)
            if cls_id is not None:
                class_ids.add(cls_id)

        return class_ids, country_code

    def get_species_by_region_ebird(
        self, region_code: str
    ) -> Tuple[Set[int], Optional[str]]:
        """
        根据州/省代码（如 "AU-QLD", "US-CA", "CN-44"）加载 eBird 离线物种列表。
        如果州级数据不存在，自动回退到国家级数据。

        Returns:
            (class_id_set, actual_region_used) 或 (set(), None)
        """
        import json
        module_dir = os.path.dirname(os.path.abspath(__file__))
        offline_dir = os.path.join(module_dir, "data", "offline_ebird_data")

        def _load_ebird_file(code: str) -> Optional[List[str]]:
            path = os.path.join(offline_dir, f"species_list_{code}.json")
            if not os.path.exists(path):
                return None
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return data
                return data.get("species", [])
            except Exception as e:
                print(_t("logs.avonet_read_ebird_failed", code=code, e=e))
                return None

        region_code = region_code.upper()
        species_codes = _load_ebird_file(region_code)
        actual_region = region_code

        if not species_codes and "-" in region_code:
            country = region_code.split("-")[0]
            species_codes = _load_ebird_file(country)
            actual_region = country if species_codes else None

        if not species_codes:
            return set(), None

        cls_map = self._load_ebird_cls_map()
        class_ids: Set[int] = set()
        for code in species_codes:
            cls_id = cls_map.get(code)
            if cls_id is not None:
                class_ids.add(cls_id)

        return class_ids, actual_region

import urllib.request

import planetary_computer
import pystac_client

print("=== 1. Testing JRC GSW monthly history GeoTIFF from JRC download site ===")
# Example tile URL for 80E, 20N (covers Raipur / Central India: tile 80E_20N)
# Standard JRC monthly history URL format:
# https://storage.googleapis.com/global-surface-water/downloads_ancillary/monthly_history/monthly_history_80E_20N.tif
# or https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GSW1_4/MonthlyHistory/
test_urls = [
    "https://storage.googleapis.com/global-surface-water/downloads_ancillary/monthly_history/monthly_history_80E_20N.tif",
    "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GSW1_4/MonthlyHistory/chunk_0.zip",
    "https://storage.googleapis.com/global-surface-water/downloads2021/occurrence/occurrence_80E_20N.tif",
]
for url in test_urls:
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"  [SUCCESS] {url} -> status {resp.status}")
    except Exception as e:
        print(f"  [FAILED] {url} -> {type(e).__name__}: {e}")

print("\n=== 2. Testing Planetary Computer collection 'jrc-gsw' ===")
catalog = pystac_client.Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1", modifier=planetary_computer.sign_inplace
)
try:
    jrc_col = catalog.get_collection("jrc-gsw")
    if jrc_col:
        print(f"  [SUCCESS] Found collection 'jrc-gsw': {jrc_col.title}")
        # Test item search for Raipur
        search = catalog.search(collections=["jrc-gsw"], bbox=[81.5, 21.1, 81.7, 21.3], limit=5)
        items = list(search.items())
        print(f"  Found {len(items)} items in jrc-gsw for Raipur: {[it.id for it in items]}")
    else:
        print("  [NOT FOUND] 'jrc-gsw' collection returned None")
except Exception as e:
    print(f"  [FAILED] 'jrc-gsw': {type(e).__name__}: {e}")

print("\n=== 3. Testing Planetary Computer collection 'esa-worldcover' ===")
try:
    wc_col = catalog.get_collection("esa-worldcover")
    if wc_col:
        print(f"  [SUCCESS] Found collection 'esa-worldcover': {wc_col.title}")
        search = catalog.search(
            collections=["esa-worldcover"], bbox=[81.5, 21.1, 81.7, 21.3], limit=5
        )
        items = list(search.items())
        print(f"  Found {len(items)} items in esa-worldcover for Raipur:")
        for it in items:
            assets = list(it.assets.keys())
            yr = it.properties.get("start_datetime", it.datetime)
            print(f"    Item: {it.id} | Year/Date: {yr} | Assets: {assets}")
    else:
        print("  [NOT FOUND] 'esa-worldcover' collection returned None")
except Exception as e:
    print(f"  [FAILED] 'esa-worldcover': {type(e).__name__}: {e}")

from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import re

URL = "https://services.cuzk.gov.cz/wfs/inspire-cp-wfs.asp"
DESCRIBE_URL = (
    "https://services.cuzk.gov.cz/wfs/inspire-cp-wfs.asp?"
    "service=WFS&request=DescribeFeatureType&version=2.0.0&typenames=CP:CadastralParcel"
)
DESCRIBE_OUT = "tools/cuzk_describe_CP_CadastralParcel.xsd"

LON = 17.2476996
LAT = 49.5919454

TEMPLATE_INTERSECTS = """<?xml version="1.0" encoding="UTF-8"?>
<wfs:GetFeature service="WFS" version="2.0.0"
 xmlns:wfs="http://www.opengis.net/wfs/2.0"
 xmlns:fes="http://www.opengis.net/fes/2.0"
 xmlns:gml="http://www.opengis.net/gml/3.2"
 xmlns:CP="http://inspire.ec.europa.eu/schemas/cp/4.0">
  <wfs:Query typeNames="CP:CadastralParcel">
    <fes:Filter>
      <fes:Intersects>
        <fes:ValueReference>{value_ref}</fes:ValueReference>
        <gml:Point srsName="urn:ogc:def:crs:EPSG::4326">
          <gml:pos>{lat} {lon}</gml:pos>
        </gml:Point>
      </fes:Intersects>
    </fes:Filter>
  </wfs:Query>
</wfs:GetFeature>
"""

TEMPLATE_OGC_INTERSECTS = """<?xml version="1.0" encoding="UTF-8"?>
<wfs:GetFeature service="WFS" version="2.0.0"
 xmlns:wfs="http://www.opengis.net/wfs/2.0"
 xmlns:ogc="http://www.opengis.net/ogc"
 xmlns:gml="http://www.opengis.net/gml/3.2"
 xmlns:CP="http://inspire.ec.europa.eu/schemas/cp/4.0">
  <wfs:Query typeNames="CP:CadastralParcel">
    <ogc:Filter>
      <ogc:Intersects>
        <ogc:PropertyName>{value_ref}</ogc:PropertyName>
        <gml:Point srsName="urn:ogc:def:crs:EPSG::4326">
          <gml:pos>{lat} {lon}</gml:pos>
        </gml:Point>
      </ogc:Intersects>
    </ogc:Filter>
  </wfs:Query>
</wfs:GetFeature>
"""


def run_test(label: str, body: str) -> dict:
    data = body.encode("utf-8")
    req = Request(URL, data=data, method="POST")
    req.add_header("Content-Type", "text/xml")
    print("---", label, "---")
    try:
        with urlopen(req, timeout=10) as resp:
            status = resp.getcode()
            content_type = resp.headers.get("Content-Type")
            payload = resp.read()
    except HTTPError as err:
        status = err.code
        content_type = err.headers.get("Content-Type") if err.headers else None
        payload = err.read() if err.fp else b""
    except URLError as err:
        print("error:", err)
        return {"status": None, "content_type": None, "text": "", "error": str(err)}
    except TimeoutError as err:
        print("error:", err)
        return {"status": None, "content_type": None, "text": "", "error": str(err)}

    text = payload.decode("utf-8", errors="replace")
    has_exception = "ExceptionReport" in text or "ServiceException" in text
    feature_count = len(re.findall(r"CadastralParcel", text))
    print("status=", status, "content_type=", content_type, "size=", len(payload))
    print("has_exception=", has_exception, "feature_count=", feature_count)
    if has_exception:
        print("exception:\n", text)
    else:
        print("preview:\n", text[:500])
    return {
        "status": status,
        "content_type": content_type,
        "text": text,
        "has_exception": has_exception,
        "feature_count": feature_count,
    }


def fetch_describe_feature_type() -> tuple[int | None, str | None, str]:
    req = Request(DESCRIBE_URL, method="GET")
    try:
        with urlopen(req, timeout=10) as resp:
            status = resp.getcode()
            content_type = resp.headers.get("Content-Type")
            payload = resp.read()
    except HTTPError as err:
        status = err.code
        content_type = err.headers.get("Content-Type") if err.headers else None
        payload = err.read() if err.fp else b""
    except URLError as err:
        print("error:", err)
        return None, None, ""

    text = payload.decode("utf-8", errors="replace")
    with open(DESCRIBE_OUT, "w", encoding="utf-8") as handle:
        handle.write(text)
    print("describe status=", status, "content_type=", content_type, "bytes=", len(payload))
    return status, content_type, text


def extract_geometry_elements(xsd_text: str) -> list[str]:
    names = []
    pattern = re.compile(r'name="([^"]+)"[^>]+type="([^"]+)"', re.IGNORECASE)
    for match in pattern.finditer(xsd_text):
        name, typ = match.groups()
        typ_lower = typ.lower()
        if any(
            key in typ_lower
            for key in (
                "geometrypropertytype",
                "surfacepropertytype",
                "multisurfacepropertytype",
                "polygonpropertytype",
                "multipolygonpropertytype",
                "pointpropertytype",
                "multipointpropertytype",
                "curvepropertytype",
                "multicurvepropertytype",
                "linestringpropertytype",
                "multilinestringpropertytype",
            )
        ):
            names.append(f"{name} ({typ})")
    return sorted(set(names))


def pick_geometry_names(names: list[str]) -> list[str]:
    if not names:
        return ["geometry"]
    return [names[0].split(" ")[0]]


if __name__ == "__main__":
    status, content_type, xsd_text = fetch_describe_feature_type()
    geom_candidates = extract_geometry_elements(xsd_text) if xsd_text else []
    print("geometry elements:", geom_candidates if geom_candidates else "none found")

    picked = pick_geometry_names(geom_candidates)
    value_refs = ["geometry", "cp:geometry"]
    for name in picked:
        value_refs.append(f"cp:{name}")
    value_refs = list(dict.fromkeys(value_refs))

    results = []
    for value_ref in value_refs:
        body = TEMPLATE_INTERSECTS.format(lon=LON, lat=LAT, value_ref=value_ref)
        results.append(run_test(f"FES Intersects value_ref={value_ref}", body))

    if all(res.get("has_exception") for res in results if res):
        ogc_ref = value_refs[-1]
        ogc_body = TEMPLATE_OGC_INTERSECTS.format(lon=LON, lat=LAT, value_ref=ogc_ref)
        run_test(f"OGC Intersects value_ref={ogc_ref}", ogc_body)

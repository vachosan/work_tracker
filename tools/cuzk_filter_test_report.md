# CUZK WFS Point Filter Test Report

Test date: 2026-01-15

## DescribeFeatureType
- URL: https://services.cuzk.gov.cz/wfs/inspire-cp-wfs.asp?service=WFS&request=DescribeFeatureType&version=2.0.0&typenames=CP:CadastralParcel
- Status: 200
- Content-Type: text/xml
- Saved: tools/cuzk_describe_CP_CadastralParcel.xsd
- Geometry-like elements detected:
  - geometry (gml:CurvePropertyType)
  - geometry (gml:GeometryPropertyType)
  - geometry (gml:MultiSurfacePropertyType)
  - referencePoint (gml:PointPropertyType)

## POST GetFeature (FES 2.0)
Test point: lon=17.2476996 lat=49.5919454

- ValueReference=geometry
  - HTTP 400
  - ExceptionReport: "Wrong filter syntax, filter unparsed!!!"

- ValueReference=cp:geometry
  - HTTP 400
  - ExceptionReport: "Wrong filter syntax, filter unparsed!!!"

## POST GetFeature (OGC 1.1.0 filter namespace)
- ValueReference=cp:geometry
  - Request timed out (read timeout), no response captured

## Conclusion
- FES 2.0 Intersects was rejected with "Wrong filter syntax" for both geometry and cp:geometry.
- OGC 1.1.0 Intersects did not return a response within timeout.
- Based on this run: spatial filter not accepted in the tested form; server may require different filter encoding or has limited filter support.

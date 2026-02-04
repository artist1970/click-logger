from flask import Flask, request, jsonify
import requests
import xml.etree.ElementTree as ET
import os

app = Flask(__name__)

# --------------------------------------------------
# CONFIG
# --------------------------------------------------

# IMPORTANT:
# Set this as an environment variable on Render
# or replace os.getenv(...) with your actual USPS USERID
USPS_USERID = os.getenv("USPS_USERID", "REPLACE_WITH_YOUR_USPS_ID")

# --------------------------------------------------
# HEALTH CHECK (for Render)
# --------------------------------------------------

@app.route("/")
def health():
    return jsonify({
        "status": "ok",
        "service": "Florida Voter Info API"
    })

# --------------------------------------------------
# ZIP CODE LOOKUP ENDPOINT
# --------------------------------------------------

@app.route("/api/zipinfo", methods=["GET"])
def zipinfo():
    zip_code = request.args.get("zip", "").strip()

    # Basic validation
    if not zip_code.isdigit() or len(zip_code) not in (5, 9):
        return jsonify({"error": "Invalid ZIP code"}), 400

    # Build USPS City/State Lookup XML
    xml_payload = f"""
    <CityStateLookupRequest USERID="{USPS_USERID}">
        <ZipCode ID="0">
            <Zip5>{zip_code[:5]}</Zip5>
        </ZipCode>
    </CityStateLookupRequest>
    """

    usps_url = (
        "https://secure.shippingapis.com/ShippingAPI.dll"
        "?API=CityStateLookup"
        f"&XML={xml_payload}"
    )

    try:
        response = requests.get(usps_url, timeout=5)

        if response.status_code != 200:
            return jsonify({"error": "USPS service unavailable"}), 502

        if "<Error>" in response.text:
            return jsonify({"error": "USPS lookup failed"}), 400

        root = ET.fromstring(response.text)

        city_el = root.find(".//City")
        state_el = root.find(".//State")

        city = city_el.text.title() if city_el is not None else None
        state = state_el.text.upper() if state_el is not None else None

        # --------------------------------------------------
        # MOCK DISTRICT / COUNTY LOGIC
        # (Replace later with full Florida ZIP dataset)
        # --------------------------------------------------

        county = "Unknown County"
        district = "Unknown District"

        if zip_code.startswith(("346", "337")):
            county = "Pinellas County"
            district = "FL-13"
        elif zip_code.startswith(("336", "335")):
            county = "Hillsborough County"
            district = "FL-14"

        # --------------------------------------------------
        # RESPONSE PAYLOAD
        # --------------------------------------------------

        return jsonify({
            "zip": zip_code,
            "city": city,
            "state": state,
            "county": county,
            "district": district,
            "issues": [
                {
                    "title": "Clean Water for Florida",
                    "link": "https://dos.elections.myflorida.com/initiatives/"
                },
                {
                    "title": "Affordable Housing Amendment",
                    "link": "https://www.myfloridahouse.gov/"
                }
            ],
            "candidates": [
                {
                    "name": "Jennifer K. Pearl",
                    "party": "Independent",
                    "site": "https://www.vervenveda.com/florida-policy"
                }
            ]
        })

    except Exception as e:
        return jsonify({
            "error": "Internal server error",
            "details": str(e)
        }), 500

# --------------------------------------------------
# RUN LOCAL SERVER
# --------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

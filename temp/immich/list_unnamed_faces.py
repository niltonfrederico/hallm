"""List Immich people with unnamed (and non-hidden) faces, plus their assets."""

from __future__ import annotations

import os
import sys

import httpx

BASE_URL = os.environ.get("IMMICH_URL", "https://immich.hallm.local")
API_KEY = os.environ["IMMICH_API_KEY"]
VERIFY_TLS = os.environ.get("IMMICH_VERIFY_TLS", "1") != "0"
ASSETS_PER_PERSON = int(os.environ.get("ASSETS_PER_PERSON", "5"))


def main() -> int:
    headers = {"x-api-key": API_KEY, "Accept": "application/json"}
    with httpx.Client(base_url=BASE_URL, headers=headers, verify=VERIFY_TLS, timeout=30) as client:
        people = fetch_unnamed_people(client)
        if not people:
            print("No unnamed faces found.")
            return 0

        print(f"Found {len(people)} unnamed people.\n")
        for person in people:
            person_id = person["id"]
            count = person.get("statistics", {}).get("assets") or "?"
            print(f"- person {person_id} ({count} assets)")
            for asset in fetch_assets_for_person(client, person_id):
                asset_id = asset["id"]
                name = asset.get("originalFileName", "")
                taken = asset.get("fileCreatedAt", "")
                print(f"    {BASE_URL}/photos/{asset_id}  {taken}  {name}")
            print()
    return 0


def fetch_unnamed_people(client: httpx.Client) -> list[dict]:
    out: list[dict] = []
    page = 1
    while True:
        resp = client.get(
            "/api/people",
            params={
                "withHidden": "false",
                "withUnnamed": "true",
                "page": page,
                "size": 500,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        chunk = data.get("people", [])
        out.extend(p for p in chunk if not (p.get("name") or "").strip())
        if not data.get("hasNextPage"):
            break
        page += 1
    return out


def fetch_assets_for_person(client: httpx.Client, person_id: str) -> list[dict]:
    resp = client.post(
        "/api/search/metadata",
        json={"personIds": [person_id], "size": ASSETS_PER_PERSON, "page": 1},
    )
    resp.raise_for_status()
    return resp.json().get("assets", {}).get("items", [])


if __name__ == "__main__":
    sys.exit(main())

"""Recover a completed upload from a prior run's receipt artifact. Never upload."""
from __future__ import annotations

import io
import json
import os
import urllib.request
import urllib.parse
import zipfile
from datetime import datetime
from zoneinfo import ZoneInfo

from upload_ledger import STATE, persist, save_state


def recover(day: str) -> bool:
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    record = state.get(day, {})
    if not record or record.get("video_id"):
        return False
    token = os.environ["GH_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]

    class SafeRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            redirected = super().redirect_request(request, fp, code, msg, headers, newurl)
            if redirected and urllib.parse.urlparse(request.full_url).netloc != urllib.parse.urlparse(newurl).netloc:
                redirected.remove_header("Authorization")
            return redirected

    opener = urllib.request.build_opener(SafeRedirect())

    def get(url):
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                                       "Accept": "application/vnd.github+json"})
        with opener.open(request, timeout=45) as response:
            return response.read()

    receipts = []
    for page in range(1, 4):
        artifacts = json.loads(get(f"https://api.github.com/repos/{repo}/actions/artifacts?per_page=100&page={page}"))["artifacts"]
        for artifact in artifacts:
            if artifact["name"] != f"pim-upload-receipt-{day}" or artifact["expired"]:
                continue
            with zipfile.ZipFile(io.BytesIO(get(artifact["archive_download_url"]))) as archive:
                info = archive.getinfo("upload_receipt.json")
                if info.file_size > 100_000:
                    raise ValueError("unexpected upload receipt artifact size")
                receipt = json.loads(archive.read(info))
            if (receipt.get("release_key", receipt.get("date_kst")) == day and receipt.get("operation_id") == record.get("operation_id")
                    and receipt.get("channel_id") == record.get("channel_id") and receipt.get("video_id")):
                receipts.append(receipt)
        if len(artifacts) < 100:
            break
    ids = {receipt["video_id"] for receipt in receipts}
    if len(ids) > 1:
        raise ValueError("conflicting upload receipts; manual reconciliation required")
    if not receipts:
        print("Upload intent has no recoverable completion receipt; a new upload will remain blocked.")
        return False
    state[day] = receipts[0]
    save_state(STATE, state)
    persist()
    print(f"Recovered completed upload receipt for {day}.")
    return True


if __name__ == "__main__":
    recover(os.environ.get("RUN_KEY") or datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat())

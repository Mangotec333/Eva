"""
EVA Google Drive Organizer
Automatically creates category folders and moves uploaded files into them.
Called after any export_files operation, or runs standalone to organize root.

Folder structure in Google Drive:
  EVA/
    Architecture/       — flowcharts, hybrid-arch, EVA status docs
    Deal Intelligence/  — EF, Flippa, Acquire.com research
    Personal Brand/     — signature talk, life architecture, LinkedIn
    Operations/         — infra README, setup guides, angel logs
    Financial/          — revenue inventory, pricing models
    Misc/               — anything unmatched
"""

import os
import pickle
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive']

TOKEN_PATH = os.path.expanduser("~/.eva/drive_token.pickle")
CREDS_PATH = os.path.expanduser("~/.eva/drive_credentials.json")

# Pattern → folder path mapping
FOLDER_MAP = {
    "EVA/Architecture": [
        "eva_architecture", "EVA_STATUS", "hybrid-architecture",
        "phase-1-macos", "infra", "sentinel", "bootstrap",
    ],
    "EVA/Deal Intelligence": [
        "empire_flippers", "acquire_com", "flippa",
        "competitor_analysis", "listings_report", "deal_scout",
        "vestedbb", "oxnard",
    ],
    "EVA/Personal Brand": [
        "signature_talk", "Signature_Talk", "Signature-talk",
        "life_architecture", "linkedin", "vineet_signature",
        "karpathy", "personal_website", "pre_thought",
        "sensory_quotient",
    ],
    "EVA/Operations": [
        "EVA_Revenue", "README", "morning_brief", "email_agent",
        "angel", "yaksha", "cron", "docker",
    ],
    "EVA/Financial": [
        "revenue", "pricing", "financial", "cashflow",
        "shopify_metrics", "heloc", "acquisition_model",
    ],
}

def get_service():
    creds = None
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, 'rb') as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        with open(TOKEN_PATH, 'wb') as f:
            pickle.dump(creds, f)
    return build('drive', 'v3', credentials=creds)

def get_or_create_folder(service, path: str) -> str:
    """Create nested path like EVA/Architecture. Returns final folder ID."""
    parts = path.split('/')
    parent_id = None
    for part in parts:
        q = f"name='{part}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_id:
            q += f" and '{parent_id}' in parents"
        results = service.files().list(q=q, fields="files(id)").execute()
        files = results.get('files', [])
        if files:
            parent_id = files[0]['id']
        else:
            meta = {'name': part, 'mimeType': 'application/vnd.google-apps.folder'}
            if parent_id:
                meta['parents'] = [parent_id]
            folder = service.files().create(body=meta, fields='id').execute()
            parent_id = folder['id']
            print(f"[Drive] Created: {part}")
    return parent_id

def match_folder(filename: str) -> str:
    name = filename.lower()
    for folder_path, patterns in FOLDER_MAP.items():
        for p in patterns:
            if p.lower() in name:
                return folder_path
    return "EVA/Misc"

def move_file(service, file_id: str, target_folder_id: str):
    meta = service.files().get(fileId=file_id, fields='parents').execute()
    old_parents = ",".join(meta.get('parents', []))
    service.files().update(
        fileId=file_id,
        addParents=target_folder_id,
        removeParents=old_parents,
        fields='id'
    ).execute()

def organize(uploaded_files: list[dict] = None):
    """
    Main entry point.
    uploaded_files: list of {"remote_file_id": "...", "file_name": "..."}
    If None: organizes all loose files in Drive root.
    """
    service = get_service()

    # Pre-build all folders
    all_paths = list(FOLDER_MAP.keys()) + ["EVA/Misc"]
    folder_ids = {p: get_or_create_folder(service, p) for p in all_paths}
    print(f"[Drive] {len(folder_ids)} folders ready")

    if uploaded_files:
        files = [{"id": f["remote_file_id"], "name": f["file_name"]} for f in uploaded_files]
    else:
        # Grab loose files from root
        res = service.files().list(
            q="'root' in parents and trashed=false and mimeType!='application/vnd.google-apps.folder'",
            fields="files(id, name)", pageSize=100
        ).execute()
        files = res.get('files', [])
        print(f"[Drive] Found {len(files)} files in root")

    moved = 0
    for f in files:
        target = match_folder(f["name"])
        move_file(service, f["id"], folder_ids[target])
        print(f"[Drive] {f['name']} → {target}")
        moved += 1

    print(f"[Drive] Done. {moved} files organized.")
    return {"organized": moved, "folders": list(folder_ids.keys())}


if __name__ == "__main__":
    # Organize files just uploaded this session
    uploaded_this_session = [
        {"remote_file_id": "19luZZl6rWCIBf6ntqfzxKta_iucmMZTU", "file_name": "eva_architecture_flowchart.pdf"},
        {"remote_file_id": "1ovxcYGloHKNwlX4f5sLj9Z8sCzsxnN-x", "file_name": "EVA_STATUS.md"},
        {"remote_file_id": "17TZ0ZEU2Y9GC6tfcvqlOsG8tumSRydzN", "file_name": "EVA_Revenue_App_Complete_Inventory.md"},
        {"remote_file_id": "1C7jUNGVT5huI6MJYVgOfPBS4GNmHMyhm", "file_name": "hybrid-architecture.md"},
        {"remote_file_id": "1rAyONn6Vlnv8Fzx1Nx7FqpfPH8BRDesT", "file_name": "README.md"},
        {"remote_file_id": "1XOCpyg_Ykzjaf5rdW3MdoxBtL0bJKL_Q", "file_name": "empire_flippers_marketplace.xlsx"},
        {"remote_file_id": "1BuQFFEckyjm7fB3J8wG0jLeUhPafD-Z1", "file_name": "empire_flippers_top3_by_category.xlsx"},
        {"remote_file_id": "1oVHz4uR0rUqgBOfN2i8uJ7STw5-I3F6m", "file_name": "acquire_com_listings_report.md"},
        {"remote_file_id": "1fR9NSexwjRt-6tvIbTF6oxcr30HchnZN", "file_name": "flippa_listings_research.md"},
        {"remote_file_id": "18fHa2HY0prIbtsdCiqcs4wL0eSh9CDMv", "file_name": "competitor_analysis.md"},
        {"remote_file_id": "1itLdOmHVq74dQXjyOu_7v6oSiKgKBNiU", "file_name": "Signature_Talk_Master.docx"},
        {"remote_file_id": "1HyCjDqmN7G0-93qgLFdrt1UnUWHUthJM", "file_name": "Signature-talk-masterclass-worksheet.docx"},
        {"remote_file_id": "1haT95KrbWRVDiFaC-M-ZEgD_BeeNkA18", "file_name": "vineet_signature_talk_v1.docx"},
        {"remote_file_id": "1slUPpKCx7vX0YU4-yduOWgj3LrT6H2Nk", "file_name": "vineet_signature_talk_v1.pdf"},
        {"remote_file_id": "11aecIWuyaGW3uEbTQtvCPAZLxhoqLDM5", "file_name": "signature-talk.md"},
        {"remote_file_id": "1QK3LSiJZocZrQ-QBA2HDVPTtcQv6S3ic", "file_name": "life_architecture.pdf"},
        {"remote_file_id": "1nv17fj_L2L8XVZN9bHIzEZHXDjxWmU_O", "file_name": "linkedin_oauth_guide.md"},
        {"remote_file_id": "1XdLsoyGFDFu6dhnc94nC5bywRT55bDwz", "file_name": "linkedin_post_templates.md"},
    ]
    organize(uploaded_this_session)

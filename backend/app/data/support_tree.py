"""Support bot decision tree, as data.

To add a topic: add an entry below and reference it from a parent's "quick_replies".
No code changes are needed. Node fields:

  message        text the bot sends when the node is reached (required)
  keywords       lowercase words/phrases; a user message containing them routes here (optional)
  quick_replies  buttons: [{"label": "...", "next": "<node id>"}] (optional)
  escalate       True = hand the chat to a human admin (optional)

Matching (see app/services/support_bot.py): a message equal to a button label wins first,
then the node with the most keyword hits, otherwise the fallback.
"""

SUPPORT_TREE = {
    "root": {
        "message": "Hi! I'm the NeighborLend helper. What do you need help with?",
        "quick_replies": [
            {"label": "Photo upload problems", "next": "photos"},
            {"label": "Handover & condition check", "next": "handover"},
            {"label": "Returns & damage", "next": "returns"},
            {"label": "Offers & pricing", "next": "offers"},
            {"label": "Listing an item", "next": "listing"},
            {"label": "Email verification", "next": "email"},
            {"label": "Talk to a human", "next": "human"},
        ],
    },
    "photos": {
        "keywords": ["photo", "upload", "image", "camera", "blurry", "file", "picture"],
        "message": (
            "Photo tips: use JPEG, PNG or WebP under 8 MB. The condition check needs all 6 views "
            "(front, back, left, right, top, bottom). Fit the whole item in the frame, use good light, "
            "and hold the phone steady. If a photo is flagged as blurry or dark you can retake it. "
            "If an upload fails, retry on a stronger connection."
        ),
        "quick_replies": [
            {"label": "Camera is blocked", "next": "camera"},
            {"label": "Still stuck", "next": "human"},
            {"label": "Back to menu", "next": "root"},
        ],
    },
    "camera": {
        "keywords": ["camera blocked", "permission", "not working", "black screen", "no camera"],
        "message": (
            "Allow camera access in your browser's site settings and reload. The camera needs an "
            "HTTPS page (the deployed site is fine). You can also tap 'Choose a file' to pick an "
            "existing photo instead."
        ),
        "quick_replies": [
            {"label": "Still stuck", "next": "human"},
            {"label": "Back to menu", "next": "root"},
        ],
    },
    "handover": {
        "keywords": ["handover", "hand over", "pickup", "condition", "before photos", "confirm receipt", "received"],
        "message": (
            "Handover: the lender takes 6 condition photos and shares a damage-check link with the "
            "borrower. The borrower reviews them and taps 'I received this item', which starts the "
            "rental clock. Lost the link? It is in your Inbox notification and on the lend page."
        ),
        "quick_replies": [
            {"label": "Link expired or broken", "next": "link_issue"},
            {"label": "Item doesn't match the photos", "next": "mismatch"},
            {"label": "Back to menu", "next": "root"},
        ],
    },
    "link_issue": {
        "keywords": ["expired", "410", "invalid link", "link not working", "link broken"],
        "message": (
            "Links expire 60 days after they are made (and are extended once the rental starts). A "
            "'closed' message means the lend is already finished. Only the lender and borrower of "
            "that lend can open it, so make sure you are signed in with the right account. If none "
            "of that explains it, ask a human."
        ),
        "quick_replies": [
            {"label": "Talk to a human", "next": "human"},
            {"label": "Back to menu", "next": "root"},
        ],
    },
    "mismatch": {
        "keywords": ["doesn't match", "does not match", "different", "already damaged", "broken on arrival"],
        "message": (
            "Do not confirm receipt yet. Use 'Report an issue' on the lend page and describe what is "
            "different; the lender is notified and borrowing will not start until it is sorted out."
        ),
        "quick_replies": [
            {"label": "Talk to a human", "next": "human"},
            {"label": "Back to menu", "next": "root"},
        ],
    },
    "returns": {
        "keywords": ["return", "damage", "dispute", "late", "overdue", "broke", "scratch", "dent"],
        "message": (
            "Returns: open your damage-check link, take the 6 return photos and submit. You can tap "
            "'Return today' to return early. The lender then has 72 hours to approve or dispute; "
            "if they do not respond it is approved automatically. A dispute goes to NeighborLend "
            "admins together with both photo sets."
        ),
        "quick_replies": [
            {"label": "I disagree with a dispute", "next": "human"},
            {"label": "Back to menu", "next": "root"},
        ],
    },
    "offers": {
        "keywords": ["offer", "price", "counter", "payment", "cost", "deposit", "pay"],
        "message": (
            "Prices are agreed in chat offers: open the conversation and use the offer panel to set "
            "the daily price and dates. A counter-offer replaces the previous pending one, and the "
            "lender's minimum price is enforced automatically. There is no online payment step yet."
        ),
        "quick_replies": [
            {"label": "Back to menu", "next": "root"},
            {"label": "Talk to a human", "next": "human"},
        ],
    },
    "listing": {
        "keywords": ["listing", "list item", "create listing", "category", "my item", "lend an item"],
        "message": (
            "When you create a listing, add clear photos (the AI suggests a category from them), "
            "set a daily price and your pickup area. Listings in an AI-supported category are "
            "checked automatically; others may wait for review."
        ),
        "quick_replies": [
            {"label": "Photo upload problems", "next": "photos"},
            {"label": "Back to menu", "next": "root"},
            {"label": "Talk to a human", "next": "human"},
        ],
    },
    "email": {
        "keywords": ["verify", "verification", "otp", "code", "email"],
        "message": (
            "Verification codes are valid for 10 minutes and can be re-sent after a minute. Check "
            "your spam folder, and make sure you typed your email address correctly."
        ),
        "quick_replies": [
            {"label": "Talk to a human", "next": "human"},
            {"label": "Back to menu", "next": "root"},
        ],
    },
    "human": {
        "escalate": True,
        "message": (
            "I've flagged this for the NeighborLend team. A human will reply here, so add any "
            "details below in the meantime."
        ),
    },
}

FALLBACK_MESSAGE = (
    "Sorry, I didn't catch that. Pick an option below, or choose 'Talk to a human'."
)

# What the bot says first when a chat is opened from a particular step. Falls back to root.
STEP_GREETING_NODE = {
    "handover_photos": "photos",
    "listing_photos": "photos",
    "return_flow": "returns",
    "dispute": "returns",
    "negotiation": "offers",
    "handover_confirm": "handover",
    "damage_link": "link_issue",
    "email_verify": "email",
    "listing_create": "listing",
}

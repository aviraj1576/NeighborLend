# YOLOE model on Render and Vercel

The backend owns inference. Both listing uploads (`POST /api/upload`) and
`POST /api/ai/identify` now use the same cached YOLOE instance. The tracked model is
`backend/ai_service/models/neighborlend_yoloe_best.pt` (about 53 MB). It contains 24
trained classes. Excluding dumbbell leaves 23 active classes, including kettle;
class IDs are never renumbered. The previous `ai_service/best_model.pt` has only
nine classes and does not include kettle.

## Deploy this change

1. Push the changed source and the existing tracked YOLOE checkpoint to
   `https://github.com/aviraj1576/NeighborLend`. Do not commit `.env` or credentials.
2. In the Render backend's Environment settings, set
   `AI_MODEL_PATH=/app/ai_service/models/neighborlend_yoloe_best.pt` for the repository's
   Docker deployment. Set `AI_CONFIDENCE_THRESHOLD=0.25`. For a native Python service
   whose root directory is `backend`, use
   `AI_MODEL_PATH=./ai_service/models/neighborlend_yoloe_best.pt` instead.
   Existing dashboard overrides must be changed even when `render.yaml` is updated.
3. Redeploy the backend from the pushed commit. The Dockerfile already copies
   `backend/ai_service`, including the checkpoint. No model download is required
   at runtime. Check the backend logs for
   `YOLOE loaded from neighborlend_yoloe_best.pt: 24 trained classes, 23 active classes`
   and `YOLOE model pre-loaded and warmed up`. Ensure INFO logs are enabled when
   checking these messages. A stale nine-class checkpoint is rejected with an
   explicit error in the logs; image uploads still work without AI predictions.
4. Vercel's production `VITE_API_BASE_URL` must be the actual Render backend URL
   ending in `/api`, for example `https://YOUR-BACKEND.onrender.com/api`. The model
   fix requires no frontend source changes. Redeploy Vercel if this variable changes.
   Render's `CORS_ORIGINS` must include the exact Vercel frontend origin.
5. Upload a fresh photo in the listing screen. In browser Developer Tools → Network,
   inspect `/api/upload` on the intended Render host. Its JSON contains `ai_label`,
   `ai_confidence`, and `detections`; these are the model's results, not fixed labels.
   A model can still misclassify an image; confidence is not proof of correctness.

The 25% default admits the supplied `barbell_lender.jpeg` prediction (25.02%)
and retains the kettle prediction (88.66%). The first `lender_barbell.jpg` is
still missed; lowering to 15% instead returns an incorrect screwdriver prediction
(20.16%). These three photos do not establish accuracy on other images.

## Local verification

From `backend`, with the project dependencies and pytest installed:

```sh
python -B -m pytest tests/test_ai_model_connectivity.py tests/test_supabase_photo_uploads.py -q
```

These tests use controlled model predictions and isolated test storage/database
configuration. To check the real checkpoint without touching the database, run
the following from `backend` with a valid private `JWT_SECRET` configured:

```sh
python -B -c "from app.services.ai_identifier import _get_model, get_allowed_classes; m = _get_model(); assert m is not None, 'Model failed to load; see logs'; ids = get_allowed_classes(m); assert len(ids) == 23; print({i: m.names[i] for i in ids})"
```

This prints the active classes, not an accuracy measurement. Confirm kettle
detection separately using representative photos on the deployed backend.

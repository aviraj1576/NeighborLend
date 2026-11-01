# Frontend component guide and listing category badge

This guide describes the React components and supporting frontend files currently under `frontend/src`, then traces how the listing category badge is populated and displayed.

## Frontend application structure

### Application entry and routing

- `main.jsx` mounts the React application into the `root` element from `frontend/index.html`, enables React Strict Mode, and loads the shared theme and global styles.
- `App.jsx` sets up browser routing and wraps the application in `AuthProvider` and a shared `MainLayout`. `MainLayout` renders the navigation bar and page content. `ProtectedRoute` waits for authentication initialization and redirects signed-out visitors to `/login`.

The routes configured in `App.jsx` are:

| Route | Page component | Access |
|---|---|---|
| `/` | `Landing` | Public |
| `/login` | `Login` | Public |
| `/register` | `Register` | Public |
| `/browse` | `Browse` | Public |
| `/listing/:id` | `ListingDetail` | Public |
| `/create-listing` | `CreateListing` | Signed-in users |
| `/create-request` | `CreateBorrowRequest` | Signed-in users |
| `/my-listings` | `MyListings` | Signed-in users |
| `/messages` and `/messages/:conversationId` | `Chat` | Signed-in users |

### Shared interface components

- `components/Navbar.jsx` renders the NeighborLend brand, navigation links, and login/signup or signed-in user actions. It adapts the navigation for mobile and calls the auth context to log out.
- `components/ListingCard.jsx` presents a listing summary: photo or placeholder, category and daily-price badges, title, location and distance, owner identity, and rating. Selecting a card opens its listing detail route. The category badge is explained in detail below.

### Page components

- `pages/Landing.jsx` is the public introduction to the service, its main benefits, how sharing works, and links into the app.
- `pages/Login.jsx` collects username/email and password, signs the user in through the auth context, and handles form feedback.
- `pages/Register.jsx` collects account details, fetches and submits the arithmetic security check, validates the password confirmation, and navigates to browsing after successful registration.
- `pages/Browse.jsx` searches listings, supports text/category/distance filtering and location selection, and renders results with `ListingCard`.
- `pages/ListingDetail.jsx` loads a selected listing and shows its description, photos, owner, location, and verification details; it can start a conversation with the lender.
- `pages/CreateListing.jsx` guides a lender through photo upload and AI identification, listing details, suggested pricing, and location before submitting the listing.
- `pages/CreateBorrowRequest.jsx` collects the item a user needs, its category and details, price/date preferences, and location, then submits a borrow request.
- `pages/MyListings.jsx` shows the signed-in user's listings and provides controls for listing status and deletion.
- `pages/Chat.jsx` displays conversations and message history, sends messages, and supports rental offers, counter-offers, acceptance, and rejection.

Each page has a corresponding stylesheet: `Browse.css`, `Chat.css`, `CreateBorrowRequest.css`, `CreateListing.css`, `Landing.css`, `ListingDetail.css`, `Login.css`, `MyListings.css`, and `Register.css`. The shared `components/` directory also contains `Navbar.css` and `ListingCard.css`.

### Shared state, API, utilities, and styling

- `context/AuthContext.jsx` provides the current user, authentication loading state, login and registration actions, logout, and the `isAuthenticated` flag. It restores a saved session by checking the stored token with the API.
- `api/client.js` creates the shared Axios client using `VITE_API_BASE_URL` (or its configured default), attaches the stored auth token to requests, and handles unauthorized responses.
- `utils/location.js` exports `detectUserLocation`, which attempts browser GPS and then IP-based lookup, and `POPULAR_LOCATIONS`, the preset location choices used by location-aware pages.
- `design/theme.css` defines shared theme tokens such as colors and gradients. `design/global.css` provides the app-wide base styles and reusable layout rules.
- `frontend/index.html` provides the browser document and React mount point. `frontend/package.json` declares the frontend dependencies and npm scripts, and `frontend/vite.config.js` configures Vite and the development server.

## Listing category badge: verified data flow

### Where the badge is rendered

The browse page maps its API results to `ListingCard` (`frontend/src/pages/Browse.jsx`). In `frontend/src/components/ListingCard.jsx`, the card renders:

```jsx
<div className="listing-category-badge">
  {listing.category || 'Item'}
</div>
```

The badge styling is in `frontend/src/components/ListingCard.css`, under `.listing-category-badge`. Its background uses `var(--accent-gradient)`, whose blue gradient is defined in `frontend/src/design/theme.css` (`#38bdf8` to `#0284c7`). The CSS `text-transform: uppercase` makes a stored value such as `Other` appear as `OTHER`. The JSX fallback is `Item`, not `Other`.

### Where the displayed value originates

The listing card receives listing objects from `Browse`, which calls `GET /listings/search`. In `backend/app/routers/listings.py`, `search_listings` queries listings and `_format_listing_out` copies `listing.category` directly into the response's `category` field. There is no category conversion or `Other` fallback in that response path. `ListingOut` in `backend/app/schemas/listing.py` also defines `category` as a required string.

For new listings, the frontend source of the submitted category is `formData.category` in `frontend/src/pages/CreateListing.jsx`. It starts as `'Other'`. The category dropdown is populated from `['Tools', 'Electronics', 'Sports', 'Party', 'Books', 'Other']`; it contains no `Bicycle` option. When submitted, `handleSubmit` sends:

```js
name: formData.title,
category: formData.category,
ai_label: aiData?.label || null,
```

The FastAPI `create_listing` function in `backend/app/routers/listings.py` passes `data.category` directly into the SQLAlchemy `Listing`. `ListingCreateIn` in `backend/app/schemas/listing.py` requires `category`; the SQLAlchemy `Listing.category` column in `backend/app/models.py` is `nullable=False` and has no model-level default. The stored value therefore comes from the submitted form/request, not a database default.

### Why `OTHER` can appear for a bicycle

The verified creation-flow explanation is: if a person enters or AI-fills a bicycle name but leaves the category dropdown unchanged, the form still submits `category: 'Other'`. The listing API stores that value, the search API returns it unchanged, and the card's uppercase CSS renders it as `OTHER`.

The upload handler in `CreateListing.jsx` updates the form's **title** from `data.ai_label` but does not update `formData.category`. It also sets an AI information object's `suggested_category` to the hard-coded string `'Other'`; that does not change the actual category form field. Thus the current UI can create a listing named `bicycle` with category `Other` unless the person manually selects one of the available categories.

This explains how the observed badge can happen, but the currently inspected database rows do **not** prove that this is what happened to the specific listing the user saw:

- The project-level `neighbourlend.db` contains a seeded `Mountain Bicycle` row with `category='Bicycle'` and `ai_label=NULL`. That row would render as `BICYCLE`, not `OTHER`.
- `NeighborLend/backend/neighborlend.db` has the same schema but no listing rows.
- The runtime can select a database URL through settings, so these two local DB checks do not identify the exact database behind the reported screen.

Consequently, the default-form explanation is verified as a code path, while the exact stored category for the reported `bicycle` card remains unverified. If its active database row has `category='Other'`, the card displays that value; if it instead has a different category, this component will display that category.

### `name`, `category`, and `ai_label`

- **`name`** is the listing's human-facing item name. The create page uses its `title` input as the payload's `name`. For a successful upload detection, it initially fills that title with the detector label; the user can edit it.
- **`category`** is a separately selected listing classification. It is the field shown on the card and is persisted in the `listings.category` database column.
- **`ai_label`** is the YOLO detection result kept separately in `listings.ai_label`, with `ai_confidence` stored separately too. `backend/app/routers/uploads.py` returns the best detection as `ai_label`; the frontend submits it independently. The create endpoint stores it in the `Listing.ai_label` field and `_format_listing_out` returns it as `ai_label`. The card JSX does not use it to render the category badge. The detail page can display the AI label/confidence separately.

The seeded example in `backend/seed_data.py` also defines `Mountain Bicycle` with category `Bicycle`, independently of any AI label, matching the category and AI fields' separate roles.

### End-to-end flow

```text
Photo upload
  -> POST /upload (backend/app/routers/uploads.py)
  -> YOLO detection returns ai_label
  -> CreateListing.processFile uses ai_label for the title
     (category remains its initial "Other" unless manually changed)
  -> CreateListing.handleSubmit sends name, category, ai_label separately
  -> POST /listings (backend/app/routers/listings.py:create_listing)
  -> Listing.name, Listing.category, Listing.ai_label stored separately
  -> GET /listings/search -> _format_listing_out returns category
  -> Browse.jsx passes result to ListingCard
  -> ListingCard.jsx renders listing.category
  -> ListingCard.css uppercases it and applies the blue gradient
```

### Viva explanation

“The blue badge is rendered by the listing card from the API's `category` field, not from the item name or the YOLO label. In listing creation, `category` defaults to `Other`; image detection can fill the name and save a separate `ai_label`, but it does not change the category input. If the category is left untouched, the backend stores and returns `Other`, and CSS displays it in uppercase as `OTHER`. The checked seeded bicycle row is actually categorized as `Bicycle`, so I cannot claim it is the exact database row behind the reported card.”

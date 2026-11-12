-- REVIEW REQUIRED before hosted use. Run with the old backend stopped and in ONE transaction.
-- No financial, offer, request, message, payment, evidence, or refund rows are changed.
SET LOCAL lock_timeout = '5s';
LOCK TABLE conversations IN ACCESS EXCLUSIVE MODE;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS listing_id VARCHAR REFERENCES listings(id);

-- Preserve ambiguous/mixed history as NULL. Backfill only an unambiguous owner-matched listing.
UPDATE conversations
SET listing_id = (
    SELECT MIN(o.listing_id) FROM negotiation_offers o
    WHERE o.conversation_id = conversations.id
)
WHERE listing_id IS NULL AND id IN (
    SELECT o.conversation_id FROM negotiation_offers o
    JOIN conversations c ON c.id = o.conversation_id
    JOIN listings l ON l.id = o.listing_id AND l.owner_id = c.lender_id
    GROUP BY o.conversation_id
    HAVING COUNT(DISTINCT o.listing_id) = 1
       AND COUNT(*) = (SELECT COUNT(*) FROM negotiation_offers all_offers
                      WHERE all_offers.conversation_id = o.conversation_id)
);

-- Existing duplicate scoped threads cause an error and rollback, requiring manual review.
-- PostgreSQL permits multiple NULLs, so legacy general/mixed conversations remain intact.
CREATE UNIQUE INDEX IF NOT EXISTS uq_conversations_participants_listing
    ON conversations (borrower_id, lender_id, listing_id);

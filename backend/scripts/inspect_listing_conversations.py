"""Read-only listing/chat diagnosis through the configured backend database identity."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / ".test-tools"), str(ROOT)]


def main():
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    from app.config import Settings

    url = make_url(Settings().database_url)
    if url.get_backend_name() != "postgresql":
        raise SystemExit("Configured database is not PostgreSQL; nothing inspected")
    engine = create_engine(url, connect_args={"connect_timeout": 12}, hide_parameters=True)
    queries = {
        "columns": """SELECT table_name,column_name,data_type,is_nullable
            FROM information_schema.columns WHERE table_schema='public'
            AND table_name IN ('conversations','messages','negotiation_offers','borrow_requests','listings')
            ORDER BY table_name,ordinal_position""",
        "indexes": """SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public'
            AND tablename IN ('conversations','messages','negotiation_offers','borrow_requests')""",
        "constraints": """SELECT c.relname, con.conname, pg_get_constraintdef(con.oid) AS definition
            FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'
            AND c.relname IN ('conversations','messages','negotiation_offers','borrow_requests','listings')""",
        "conversations": """SELECT c.id,b.username AS borrower,l.username AS lender,
            (SELECT count(*) FROM messages m WHERE m.conversation_id=c.id) AS message_count,
            (SELECT count(DISTINCT o.listing_id) FROM negotiation_offers o WHERE o.conversation_id=c.id) AS listing_count
            FROM conversations c JOIN users b ON b.id=c.borrower_id JOIN users l ON l.id=c.lender_id
            WHERE b.username='aarav_mehta' AND l.username='rohan_kapoor'""",
        "offers": """SELECT o.id,o.conversation_id,o.listing_id,l.name,o.status,o.daily_price,
            o.security_deposit_paise,o.start_date,o.end_date,o.borrow_request_id
            FROM negotiation_offers o JOIN conversations c ON c.id=o.conversation_id
            JOIN users b ON b.id=c.borrower_id JOIN users owner ON owner.id=c.lender_id
            LEFT JOIN listings l ON l.id=o.listing_id
            WHERE b.username='aarav_mehta' AND owner.username='rohan_kapoor' ORDER BY o.created_at""",
        "listings": """SELECT l.id,l.name,l.price_per_day,l.security_deposit,l.status
            FROM listings l JOIN users u ON u.id=l.owner_id WHERE u.username='rohan_kapoor'""",
        "duplicate_participant_threads": """SELECT c.borrower_id,c.lender_id,count(*) AS threads
            FROM conversations c GROUP BY c.borrower_id,c.lender_id HAVING count(*)>1""",
        "duplicate_offer_requests": """SELECT borrow_request_id,count(*) AS offers
            FROM negotiation_offers WHERE borrow_request_id IS NOT NULL
            GROUP BY borrow_request_id HAVING count(*)>1""",
        "request_links": """SELECT r.id,r.listing_id,r.max_price_per_day,r.total_cost,r.handover_status,
            r.borrowing_started_at,r.returned_at,b.id AS booking_id,b.offer_id,b.payment_status
            FROM borrow_requests r JOIN users u ON u.id=r.borrower_id
            LEFT JOIN rental_bookings b ON b.borrow_request_id=r.id
            WHERE u.username='aarav_mehta'""",
    }
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("BEGIN READ ONLY")
            connection.exec_driver_sql("SET LOCAL statement_timeout='15s'")
            report = {name: [dict(row) for row in connection.execute(text(sql)).mappings()]
                      for name, sql in queries.items()}
            connection.rollback()
        target = ROOT / ".payment-verification/listing-conversations/hosted-read-only.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(json.dumps({"read_only": True, "report": str(target),
                          "conversations": len(report["conversations"]),
                          "offers": len(report["offers"]), "listings": len(report["listings"])}))
        return 0
    except Exception as exc:
        # Never leak driver errors containing usernames, hosts, or credentials.
        print(json.dumps({"read_only": True, "inspection": "failed", "error_type": type(exc).__name__}))
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())

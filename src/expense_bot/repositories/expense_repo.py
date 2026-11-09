from datetime import date
from decimal import Decimal
from typing import Any, Sequence
from sqlalchemy import text, bindparam
from sqlalchemy.orm import Session


class ExpenseRepository:
    def __init__(self, session: Session):
        self.session = session

    # ---------------------------------------------------------
    # Categories
    # ---------------------------------------------------------

    def get_categories(self, user_id: int) -> list[dict[str, Any]]:
        """Fetch all categories for a user (default and custom)."""
        query = text(
            """
            SELECT id, user_id, name, is_custom, created_at
            FROM categories
            WHERE user_id = :user_id
            ORDER BY name ASC
            """
        )
        rows = self.session.execute(query, {"user_id": user_id}).mappings().all()
        return [dict(row) for row in rows]

    def get_or_create_category(self, user_id: int, category_name: str) -> int:
        """Finds existing category ID (case-insensitive) or onboards a new custom category."""
        clean_name = category_name.strip()
        select_query = text(
            """
            SELECT id FROM categories 
            WHERE user_id = :user_id AND LOWER(TRIM(name)) = LOWER(:name)
            LIMIT 1
            """
        )
        row = self.session.execute(
            select_query, {"user_id": user_id, "name": clean_name}
        ).first()

        if row:
            return row[0]

        insert_query = text(
            """
            INSERT INTO categories (user_id, name, is_custom, created_at)
            VALUES (:user_id, :name, 1, CURRENT_TIMESTAMP)
            """
        )
        result = self.session.execute(
            insert_query, {"user_id": user_id, "name": clean_name.title()}
        )
        self.session.commit()
        return result.lastrowid

    # ---------------------------------------------------------
    # LLM Audit Logging
    # ---------------------------------------------------------

    def log_llm_call(
        self,
        user_id: int,
        task: str,
        model_name: str,
        latency_ms: int,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        raw_prompt: str | None = None,
        raw_response: str | None = None,
        status: str = "success",
        error_message: str | None = None,
    ) -> int:
        """Record an LLM inference call for observability and token auditing."""
        query = text(
            """
            INSERT INTO llm_calls (
                user_id, task, model_name, latency_ms,
                prompt_tokens, completion_tokens, total_tokens,
                raw_prompt, raw_response, status, error_message, created_at
            )
            VALUES (
                :user_id, :task, :model_name, :latency_ms,
                :prompt_tokens, :completion_tokens, :total_tokens,
                :raw_prompt, :raw_response, :status, :error_message, CURRENT_TIMESTAMP
            )
            """
        )
        result = self.session.execute(
            query,
            {
                "user_id": user_id,
                "task": task,
                "model_name": model_name,
                "latency_ms": latency_ms,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "raw_prompt": raw_prompt,
                "raw_response": raw_response,
                "status": status,
                "error_message": error_message,
            },
        )
        self.session.commit()
        return result.lastrowid

    # ---------------------------------------------------------
    # Expenses Ledger & Reporting
    # ---------------------------------------------------------

    def add_expense(
        self,
        user_id: int,
        category_id: int,
        amount: Decimal | float,
        spent_on: date,
        merchant: str | None = None,
        note: str | None = None,
        llm_call_id: int | None = None,
        source: str = "text",
        currency: str = "INR",
    ) -> int:
        """Insert a confirmed expense record and return its primary key."""
        query = text(
            """
            INSERT INTO expenses (
                user_id, category_id, amount, currency, merchant,
                note, spent_on, llm_call_id, source, created_at
            )
            VALUES (
                :user_id, :category_id, :amount, :currency, :merchant,
                :note, :spent_on, :llm_call_id, :source, CURRENT_TIMESTAMP
            )
            """
        )
        result = self.session.execute(
            query,
            {
                "user_id": user_id,
                "category_id": category_id,
                "amount": float(amount),
                "currency": currency,
                "merchant": merchant,
                "note": note,
                "spent_on": spent_on,
                "llm_call_id": llm_call_id,
                "source": source,
            },
        )
        self.session.commit()
        return result.lastrowid

    def get_expenses_for_date(self, user_id: int, target_date: date) -> list[dict[str, Any]]:
        """Fetch all active expenses for a user on a specific day joined with category."""
        query = text(
            """
            SELECT 
                e.id, e.amount, e.currency, e.merchant, e.note, 
                e.spent_on, e.source, e.created_at,
                c.name AS category_name
            FROM expenses e
            JOIN categories c ON e.category_id = c.id
            WHERE e.user_id = :user_id 
              AND e.spent_on = :spent_on 
              AND e.deleted_at IS NULL
            ORDER BY e.id DESC
            """
        )
        rows = self.session.execute(
            query, {"user_id": user_id, "spent_on": target_date}
        ).mappings().all()
        return [dict(r) for r in rows]

    def get_monthly_summary(
        self, user_id: int, start_date: date, end_date: date
    ) -> dict[str, Any]:
        """Calculates total spend, transaction count, and average for a date range."""
        query = text(
            """
            SELECT 
                COALESCE(SUM(amount), 0) AS total_amount,
                COUNT(id) AS total_count,
                COALESCE(AVG(amount), 0) AS average_amount
            FROM expenses
            WHERE user_id = :user_id
              AND spent_on >= :start_date
              AND spent_on <= :end_date
              AND deleted_at IS NULL
            """
        )
        row = self.session.execute(
            query,
            {
                "user_id": user_id,
                "start_date": start_date,
                "end_date": end_date,
            },
        ).mappings().first()
        return dict(row) if row else {"total_amount": 0, "total_count": 0, "average_amount": 0}

    def get_monthly_breakdown_by_category(
        self, user_id: int, start_date: date, end_date: date
    ) -> list[dict[str, Any]]:
        """Groups spending by category for a date range, sorted by highest spent."""
        query = text(
            """
            SELECT 
                c.name AS category_name,
                SUM(e.amount) AS category_total,
                COUNT(e.id) AS expense_count
            FROM expenses e
            JOIN categories c ON e.category_id = c.id
            WHERE e.user_id = :user_id
              AND e.spent_on >= :start_date
              AND e.spent_on <= :end_date
              AND deleted_at IS NULL
            GROUP BY c.name
            ORDER BY category_total DESC
            """
        )
        rows = self.session.execute(
            query,
            {
                "user_id": user_id,
                "start_date": start_date,
                "end_date": end_date,
            },
        ).mappings().all()
        return [dict(r) for r in rows]

    # ==========================================
    # Analytics Queries
    # ==========================================

    def get_summary_range(
        self,
        user_id: int,
        start_date: date,
        end_date: date,
        category_name: str | None = None,
    ) -> dict[str, Any]:
        """Aggregate totals, counts, and averages within a date range with optional category filter."""
        query_str = """
            SELECT 
                COALESCE(SUM(e.amount), 0.0) AS total_amount,
                COUNT(e.id) AS total_count,
                COALESCE(AVG(e.amount), 0.0) AS average_amount
            FROM expenses e
            JOIN categories c ON e.category_id = c.id
            WHERE e.user_id = :user_id
              AND e.spent_on >= :start_date
              AND e.spent_on <= :end_date
        """
        params: dict[str, Any] = {
            "user_id": user_id,
            "start_date": start_date,
            "end_date": end_date,
        }

        if category_name:
            query_str += " AND LOWER(c.name) = LOWER(:category_name)"
            params["category_name"] = category_name

        result = self.session.execute(text(query_str), params).mappings().one()
        return dict(result)

    def get_breakdown_range(
        self,
        user_id: int,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """Category-wise totals ordered by spend for the date range."""
        query_str = """
            SELECT 
                c.name AS category_name,
                COALESCE(SUM(e.amount), 0.0) AS category_total,
                COUNT(e.id) AS expense_count
            FROM expenses e
            JOIN categories c ON e.category_id = c.id
            WHERE e.user_id = :user_id
              AND e.spent_on >= :start_date
              AND e.spent_on <= :end_date
            GROUP BY c.id, c.name
            ORDER BY category_total DESC
        """
        params = {
            "user_id": user_id,
            "start_date": start_date,
            "end_date": end_date,
        }
        results = self.session.execute(text(query_str), params).mappings().all()
        return [dict(row) for row in results]

    # ==========================================
    # Delete / Undo Operations
    # ==========================================

    def delete_last_expense(self, user_id: int) -> dict[str, Any] | None:
        """Finds and deletes the most recent expense logged by this user."""
        select_query = text(
            """
            SELECT e.id, e.amount, e.merchant, e.note, e.spent_on, c.name AS category_name
            FROM expenses e
            JOIN categories c ON e.category_id = c.id
            WHERE e.user_id = :user_id
            ORDER BY e.created_at DESC, e.id DESC
            LIMIT 1
            """
        )
        row = (
            self.session.execute(select_query, {"user_id": user_id})
            .mappings()
            .first()
        )
        if not row:
            return None

        expense_data = dict(row)
        delete_query = text(
            "DELETE FROM expenses WHERE id = :id AND user_id = :user_id"
        )
        self.session.execute(
            delete_query, {"id": expense_data["id"], "user_id": user_id}
        )
        self.session.commit()
        return expense_data

    def delete_specific_expenses(
        self,
        user_id: int,
        amount: float | None = None,
        merchant: str | None = None,
        spent_on: date | None = None,
    ) -> list[dict[str, Any]]:
        """Deletes expenses matching specific search filters (at least one filter required)."""
        conditions = ["e.user_id = :user_id"]
        params: dict[str, Any] = {"user_id": user_id}

        if amount is not None:
            conditions.append("e.amount = :amount")
            params["amount"] = amount
        if merchant:
            conditions.append("LOWER(e.merchant) LIKE LOWER(:merchant)")
            params["merchant"] = f"%{merchant}%"
        if spent_on:
            conditions.append("e.spent_on = :spent_on")
            params["spent_on"] = spent_on

        where_clause = " AND ".join(conditions)

        # 1. Fetch targets before deleting so we can inform the user what was deleted
        select_query = text(
            f"""
            SELECT e.id, e.amount, e.merchant, e.note, e.spent_on, c.name AS category_name
            FROM expenses e
            JOIN categories c ON e.category_id = c.id
            WHERE {where_clause}
            ORDER BY e.created_at DESC
            LIMIT 5
            """
        )
        rows = self.session.execute(select_query, params).mappings().all()
        if not rows:
            return []

        deleted_items = [dict(r) for r in rows]
        ids = [d["id"] for d in deleted_items]

        # 2. Delete those specific records
        id_placeholders = ", ".join(f":id_{i}" for i in range(len(ids)))
        delete_params = {f"id_{i}": val for i, val in enumerate(ids)}
        delete_params["user_id"] = user_id

        delete_query = text(
            f"DELETE FROM expenses WHERE user_id = :user_id AND id IN ({id_placeholders})"
        )
        self.session.execute(delete_query, delete_params)
        self.session.commit()

        return deleted_items

    def preview_deletion(
        self, user_id: int, sql_where_clause: str
    ) -> list[dict[str, Any]]:
        """Queries matching rows using the agent's WHERE clause, strictly sandboxed to the user."""
        sanitized_clause = (
            sql_where_clause.strip().removeprefix("WHERE").removeprefix("where")
        )

        query = text(
            f"""
            SELECT e.id, e.amount, e.merchant, e.note, e.spent_on, c.name AS category_name
            FROM expenses e
            JOIN categories c ON e.category_id = c.id
            WHERE e.user_id = :user_id AND ({sanitized_clause})
            ORDER BY e.spent_on DESC, e.id DESC
            LIMIT 50
            """
        )
        rows = self.session.execute(query, {"user_id": user_id}).mappings().all()
        return [dict(r) for r in rows]

    def execute_deletion_by_ids(self, user_id: int, ids: list[int]) -> int:
        """Deletes exact IDs confirmed by the user."""
        if not ids:
            return 0

        id_placeholders = ", ".join(f":id_{i}" for i in range(len(ids)))
        params = {f"id_{i}": val for i, val in enumerate(ids)}
        params["user_id"] = user_id

        delete_query = text(
            f"DELETE FROM expenses WHERE user_id = :user_id AND id IN ({id_placeholders})"
        )
        result = self.session.execute(delete_query, params)
        self.session.commit()
        return result.rowcount


    def add_new_category(self, user_id: int, name: str) -> tuple[int, bool]:
        """
        Create a new category in categories table. Returns (category_id, created)
        where created is True if newly inserted, False if already exists.
        """
        new_category_name = name.strip()

        # 1. Check if category already exists (case-insensitive)
        check_query = text(
            "SELECT id FROM categories WHERE user_id = :user_id AND LOWER(name) = LOWER(:name)"
        )
        result_category = self.session.execute(
            check_query,
            {"user_id": user_id, "name": new_category_name},
        ).first()

        if result_category:
            # result_category is a Row object (e.g. (4,)), so return the first column
            return int(result_category[0]), False

        # 2. Insert new custom category
        insert_query = text(
            """
            INSERT INTO categories (user_id, name, is_custom, created_at)
            VALUES (:user_id, :name, 1, CURRENT_TIMESTAMP)
            """
        )
        cursor = self.session.execute(
            insert_query,
            {"user_id": user_id, "name": new_category_name},
        )
        self.session.commit()

        # 3. Retrieve the newly generated ID
        new_id = cursor.lastrowid

        return int(new_id), True


    def delete_categories(
        self,
        user_id: int,
        targets: int | str | Sequence[int | str],
        reassign_to: int | str | None = "Other",
    ) -> dict[str, int | list[str]]:
        """
        Deletes single or multiple custom categories for a user.
        Uses expanding=True bindparams so SQLite receives properly formatted IN clauses.
        """
        if isinstance(targets, (int, str)):
            raw_targets = [targets]
        else:
            raw_targets = list(targets)

        if not raw_targets:
            return {"deleted_count": 0, "deleted_names": [], "skipped_names": []}

        target_ids: list[int] = []
        target_names: list[str] = []
        for t in raw_targets:
            if isinstance(t, int) or (isinstance(t, str) and t.strip().isdigit()):
                target_ids.append(int(t))
            else:
                target_names.append(str(t).strip().lower())

        # Ensure empty lists have a fallback element so IN clause remains valid
        if not target_ids:
            target_ids = [-1]
        if not target_names:
            target_names = ["__dummy_nonexistent_category__"]

        # 1. Fetch matching categories with expanding bindparams
        find_query = (
            text("""
                SELECT id, name, is_custom 
                FROM categories 
                WHERE user_id = :user_id 
                AND (
                    id IN :target_ids 
                    OR LOWER(name) IN :target_names
                )
            """)
            .bindparams(
                bindparam("target_ids", expanding=True),
                bindparam("target_names", expanding=True),
            )
        )

        found_rows = self.session.execute(
            find_query,
            {
                "user_id": user_id,
                "target_ids": target_ids,
                "target_names": target_names,
            },
        ).fetchall()

        if not found_rows:
            return {"deleted_count": 0, "deleted_names": [], "skipped_names": []}

        # Separate deletable custom categories from protected default categories
        deletable_cats = [row for row in found_rows if row.is_custom]
        skipped_names = [row.name for row in found_rows if not row.is_custom]

        if not deletable_cats:
            return {"deleted_count": 0, "deleted_names": [], "skipped_names": skipped_names}

        deletable_ids = [cat.id for cat in deletable_cats]

        # 2. Resolve fallback category for linked expenses if reassign_to is set
        fallback_cat_id = None
        if reassign_to is not None:
            if isinstance(reassign_to, int) or (isinstance(reassign_to, str) and reassign_to.isdigit()):
                fallback_check = text("SELECT id FROM categories WHERE user_id = :user_id AND id = :cid")
                res = self.session.execute(fallback_check, {"user_id": user_id, "cid": int(reassign_to)}).first()
                if res:
                    fallback_cat_id = res[0]
            else:
                fallback_check = text(
                    "SELECT id FROM categories WHERE user_id = :user_id AND LOWER(name) = LOWER(:name)"
                )
                res = self.session.execute(
                    fallback_check, {"user_id": user_id, "name": str(reassign_to).strip()}
                ).first()
                if res:
                    fallback_cat_id = res[0]

        # 3. Handle linked expenses
        if fallback_cat_id:
            reassign_stmt = (
                text("""
                    UPDATE expenses 
                    SET category_id = :fallback_id 
                    WHERE user_id = :user_id AND category_id IN :cat_ids
                """)
                .bindparams(bindparam("cat_ids", expanding=True))
            )
            self.session.execute(
                reassign_stmt,
                {
                    "user_id": user_id,
                    "fallback_id": fallback_cat_id,
                    "cat_ids": deletable_ids,
                },
            )
        else:
            check_expenses = (
                text("""
                    SELECT DISTINCT category_id FROM expenses 
                    WHERE user_id = :user_id AND category_id IN :cat_ids
                """)
                .bindparams(bindparam("cat_ids", expanding=True))
            )
            active_cat_ids = {
                r[0] for r in self.session.execute(
                    check_expenses, 
                    {"user_id": user_id, "cat_ids": deletable_ids}
                ).fetchall()
            }
            
            deletable_cats = [cat for cat in deletable_cats if cat.id not in active_cat_ids]
            skipped_names.extend([cat.name for cat in found_rows if cat.id in active_cat_ids])
            deletable_ids = [cat.id for cat in deletable_cats]

        if not deletable_ids:
            return {"deleted_count": 0, "deleted_names": [], "skipped_names": skipped_names}

        # 4. Perform Deletion
        del_stmt = (
            text("""
                DELETE FROM categories 
                WHERE user_id = :user_id AND id IN :cat_ids
            """)
            .bindparams(bindparam("cat_ids", expanding=True))
        )
        self.session.execute(del_stmt, {"user_id": user_id, "cat_ids": deletable_ids})
        self.session.commit()

        deleted_names = [cat.name for cat in deletable_cats]
        return {
            "deleted_count": len(deleted_names),
            "deleted_names": deleted_names,
            "skipped_names": skipped_names,
        }


    def set_budget(self, user_id: int, category_name: str, limit: float) -> tuple[str, bool]:
        """
        Sets or updates a monthly budget.
        'overall' maps to category_id = NULL.
        Returns (target_display_name, created).
        """
        is_overall = category_name.strip().lower() == "overall"
        category_id = None
        display_name = "Overall"

        if not is_overall:
            cat_check = text("SELECT id, name FROM categories WHERE user_id = :user_id AND LOWER(name) = LOWER(:name)")
            row = self.session.execute(cat_check, {"user_id": user_id, "name": category_name.strip()}).first()
            if not row:
                # If category doesn't exist, create it
                cat_id, _ = self.add_new_category(user_id, category_name.strip())
                category_id = cat_id
                display_name = category_name.strip().title()
            else:
                category_id = row[0]
                display_name = row[1]

        # Check existing budget
        if category_id is None:
            check_stmt = text("SELECT id FROM budgets WHERE user_id = :user_id AND category_id IS NULL")
            params = {"user_id": user_id}
        else:
            check_stmt = text("SELECT id FROM budgets WHERE user_id = :user_id AND category_id = :cid")
            params = {"user_id": user_id, "cid": category_id}

        existing = self.session.execute(check_stmt, params).first()

        if existing:
            update_stmt = text("UPDATE budgets SET monthly_limit = :limit WHERE id = :id")
            self.session.execute(update_stmt, {"limit": limit, "id": existing[0]})
            self.session.commit()
            return display_name, False
        else:
            insert_stmt = text("""
                INSERT INTO budgets (user_id, category_id, monthly_limit, created_at)
                VALUES (:user_id, :category_id, :limit, CURRENT_TIMESTAMP)
            """)
            self.session.execute(insert_stmt, {"user_id": user_id, "category_id": category_id, "limit": limit})
            self.session.commit()
            return display_name, True

    def delete_budget(self, user_id: int, category_name: str) -> bool:
        """Deletes a budget limit."""
        is_overall = category_name.strip().lower() == "overall"
        if is_overall:
            stmt = text("DELETE FROM budgets WHERE user_id = :user_id AND category_id IS NULL")
            res = self.session.execute(stmt, {"user_id": user_id})
        else:
            stmt = text("""
                DELETE FROM budgets 
                WHERE user_id = :user_id 
                  AND category_id IN (
                      SELECT id FROM categories WHERE user_id = :user_id AND LOWER(name) = LOWER(:name)
                  )
            """)
            res = self.session.execute(stmt, {"user_id": user_id, "name": category_name.strip()})
        self.session.commit()
        return res.rowcount > 0

    def get_budgets_progress(self, user_id: int, reference_date: date | None = None) -> list[dict]:
        """
        Retrieves all active budgets and calculates current spend for the given month.
        """
        ref = reference_date or date.today()
        start_of_month = ref.replace(day=1).isoformat()
        
        # Calculate next month start for boundary
        if ref.month == 12:
            end_of_month = date(ref.year + 1, 1, 1).isoformat()
        else:
            end_of_month = date(ref.year, ref.month + 1, 1).isoformat()

        query = text("""
            SELECT 
                b.id,
                b.category_id,
                c.name AS category_name,
                b.monthly_limit,
                COALESCE(
                    (
                        SELECT SUM(amount)
                        FROM expenses e
                        WHERE e.user_id = b.user_id
                          AND (b.category_id IS NULL OR e.category_id = b.category_id)
                          AND e.spent_on >= :start_date
                          AND e.spent_on < :end_date
                    ),
                    0
                ) AS current_spend
            FROM budgets b
            LEFT JOIN categories c ON b.category_id = c.id
            WHERE b.user_id = :user_id
            ORDER BY b.category_id IS NOT NULL, c.name ASC
        """)

        rows = self.session.execute(
            query,
            {"user_id": user_id, "start_date": start_of_month, "end_date": end_of_month},
        ).fetchall()

        results = []
        for r in rows:
            name = "Overall" if r.category_id is None else (r.category_name or "Unknown")
            limit = float(r.monthly_limit)
            spent = float(r.current_spend)
            pct = (spent / limit * 100) if limit > 0 else 0.0
            results.append({
                "category_id": r.category_id,
                "name": name,
                "limit": limit,
                "spent": spent,
                "percentage": pct,
            })
        return results

    def check_budget_alerts(self, user_id: int, category_ids: list[int], reference_date: date | None = None) -> list[str]:
        """
        Evaluates category and overall budgets after logging expenses.
        Returns a list of warning strings if spend is >= 80% or >= 100%.
        """
        budgets = self.get_budgets_progress(user_id, reference_date)
        alerts = []

        cat_id_set = set(category_ids)
        for b in budgets:
            # Check if this budget is relevant (either Overall or one of the touched categories)
            if b["category_id"] is None or b["category_id"] in cat_id_set:
                pct = b["percentage"]
                if pct >= 100:
                    alerts.append(
                        f"🚨 *Exceeded Budget:* `{b['name']}` spend is at *₹{b['spent']:,.2f}* of *₹{b['limit']:,.2f}* ({pct:.1f}%)"
                    )
                elif pct >= 80:
                    alerts.append(
                        f"⚠️ *Budget Warning:* `{b['name']}` spend is at *₹{b['spent']:,.2f}* of *₹{b['limit']:,.2f}* ({pct:.1f}%)"
                    )
        return alerts
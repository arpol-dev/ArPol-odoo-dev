=================================
POS Payment Method Correction
=================================

Correct, after the session is closed, the payment method of a point of sale payment
(cash to bank or bank to cash) and propagate the effect to the cash balances.

Usage
=====

Open a closed POS session payment (list or form view), then choose the action
*Correct payment method* in the *Action* menu. The wizard:

* asks for the new payment method (limited to the methods of the point of sale);
* shows the change of the theoretical cash balance of the session;
* lists the following sessions of the same point of sale with their opening and
  closing cash before and after the correction. Lines can be edited or removed
  before applying the correction.

Accounting
==========

The correction is made in place on the posted accounting entries:

* the session entry (receivable line per payment method) is reset to draft, adjusted
  and posted again;
* the cash statement line (cash method) or the account payment (bank method) the line
  is reconciled with is adjusted accordingly, or removed when its amount becomes zero;
* the lines are reconciled again.

No account is hardcoded: the module reuses the receivable lines, statement lines and
account payments of the session, and the accounts configured on the payment methods
and on the company. It adapts to any chart of accounts.

Limits
======

* Only the payments of a **closed** session can be corrected. The cash of an open
  session is not touched.
* Only the sessions of **the same point of sale** are propagated, following the
  chain of opening cash used by Odoo (the opening cash of a session is the closing
  cash of the previous session of the same point of sale).
* The propagation is a constant shift of the cash balances. Counted differences
  (closing cash counted different from the theoretical one) are preserved. The
  counted cash is not recounted: the closing cash is moved by the same amount.
* The lines edited or removed in the wizard are applied as given. Removing a
  following session breaks the chain for the sessions after it: the user is
  responsible for that choice.
* **Company currency only.** Sessions in another currency (for example a CHF point
  of sale) are refused.
* **Pay later** payments cannot be corrected. Changing the sign of a payment (refund)
  is refused.
* The payment must be reconciled with a single cash statement line or a single
  account payment. Payments on invoiced orders, or with a different reconciliation,
  are refused by the module: nothing is changed in that case.
* A receivable line whose amount becomes zero is kept at zero, because Odoo does not
  allow deleting receivable lines of a session entry. Cash statement lines and account
  payments that become zero are deleted.
* Lock dates are not checked by the module. Odoo raises an error if a lock date
  prevents the reset to draft or the posting of an entry, and the whole correction is
  then rolled back.
* No message is posted in the chatter of the session or of the payment. The
  correction leaves no trace in Odoo besides the new payment method and the
  adjusted accounting entries.
* Tested on Odoo 18 community with the test chart of accounts of the POS test suite,
  and rehearsed on a restored copy of the production database (session with a
  cash payment changed to a bank payment, following sessions checked).

Compatibility
=============

Odoo 18.0. Depends only on ``point_of_sale``.

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AccountAccount(models.Model):
    _inherit = 'account.account'

    # =========================================================
    # IMPORT FIELD
    # =========================================================

    group_id = fields.Many2one(
        'account.group',
        string='Account Group',
        store=True,
        readonly=False,
        domain="[('level', '=', 3)]",
    )

    group_name_import = fields.Char(
        string='Account Group Name',
    )
 
    # =========================================================
    # LEVEL 2 GROUP
    # =========================================================

    level_2_group_id = fields.Many2one(
        'account.group',
        string='Level 2 Group',
        compute='_compute_legacy_groups',
        store=True,
        readonly=True,
        domain="[('level', '=', 2)]",
    )

    # =========================================================
    # LEVEL 1 GROUP
    # =========================================================

    level_1_group_id = fields.Many2one(
        'account.group',
        string='Level 1 Group',
        compute='_compute_legacy_groups',
        store=True,
        readonly=True,
        domain="[('level', '=', 1)]",
    )

    # =========================================================
    # NATIVE ODOO GROUP COMPUTATION
    # =========================================================

    @api.depends('code', 'group_name_import')
    def _compute_account_group(self):

        AccountGroup = self.env['account.group']

        for account in self:

            # -------------------------------------------------
            # If Account Group Name came from Excel
            # -------------------------------------------------

            if account.group_name_import:

                group_name = account.group_name_import.strip()

                if not group_name:
                    account.group_id = False
                    continue

                groups = AccountGroup.search([
                    ('name', '=', group_name),
                    ('level', '=', 3),
                ])

                # -------------------------------------------------
                # Group not found
                # -------------------------------------------------

                if not groups:

                    raise ValidationError(
                        "Account Group not found.\n\n"
                        "Account Code: %s\n"
                        "Account Group Name: %s\n"
                        "Required Level: 3\n\n"
                        "Please create this Level 3 Account Group first."
                        % (
                            account.code or '',
                            group_name,
                        )
                    )

                # -------------------------------------------------
                # Duplicate group name
                # -------------------------------------------------

                if len(groups) > 1:

                    raise ValidationError(
                        "Multiple Level 3 Account Groups found.\n\n"
                        "Account Group Name: %s\n\n"
                        "Please make the Level 3 group name unique."
                        % group_name
                    )

                # -------------------------------------------------
                # IMPORTANT
                # Set native Odoo group_id
                # -------------------------------------------------

                account.group_id = groups[0]

            else:

                # -------------------------------------------------
                # No imported group name
                #
                # Use original Odoo behavior
                # -------------------------------------------------

                super(
                    AccountAccount,
                    account
                )._compute_account_group()

    # =========================================================
    # LEVEL 2 / LEVEL 1 COMPUTATION
    # =========================================================

    @api.depends(
        'group_id',
        'group_id.level',
        'group_id.parent_group_id',
        'group_id.parent_group_id.level',
        'group_id.parent_group_id.parent_group_id',
        'group_id.parent_group_id.parent_group_id.level',
    )
    def _compute_legacy_groups(self):

        for account in self:

            account.level_2_group_id = False
            account.level_1_group_id = False

            # -------------------------------------------------
            # Group must exist
            # -------------------------------------------------

            level_3 = account.group_id

            if not level_3:
                continue

            # -------------------------------------------------
            # Group must be Level 3
            # -------------------------------------------------

            if level_3.level != 3:
                continue

            # -------------------------------------------------
            # Level 3 -> Level 2
            # -------------------------------------------------

            level_2 = level_3.parent_group_id

            if not level_2:
                continue

            if level_2.level != 2:
                continue

            account.level_2_group_id = level_2

            # -------------------------------------------------
            # Level 2 -> Level 1
            # -------------------------------------------------

            level_1 = level_2.parent_group_id

            if not level_1:
                continue

            if level_1.level != 1:
                continue

            account.level_1_group_id = level_1
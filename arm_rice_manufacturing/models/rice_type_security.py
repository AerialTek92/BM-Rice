# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from typing import Any, Dict, List

# --- Security group per Rice Type (Protocol 1.3: searchable constants) ---
# Reuses the EXISTING segregation groups from manufacturing_security.xml.
RICE_TYPE_GROUP_XMLIDS: Dict[str, str] = {
    'irri': 'arm_rice_manufacturing.group_bm1_irri',
    'basmati': 'arm_rice_manufacturing.group_bm2_basmati',
}
SYSTEM_ADMIN_GROUP: str = 'base.group_system'


class ProcessRiceSpec(models.Model):
    """Protocol 3.2 (OCP): rice-type segregation added WITHOUT touching the
    original process_rice_specification.py - everything here extends it."""

    _inherit = 'process.rice.spec'

    is_rice_type_locked = fields.Boolean(
        string='Rice Type Locked',
        compute='_compute_is_rice_type_locked',
        help="True when the current user belongs to exactly one Rice Type group "
             "(BM-1/IRRI or BM-2/Basmati): their Rice Type is then forced and read-only.",
    )

    # ==========================================================
    # USER RESOLUTION
    # ==========================================================

    @api.model
    def _get_user_rice_type(self) -> str:
        """Protocol 2.1 (SRP): the single rice type this user is restricted to.
        Empty string when unrestricted (admin, member of both groups, or of
        neither)."""
        if self.env.user.has_group(SYSTEM_ADMIN_GROUP):
            return ''

        memberships = [
            rice_type
            for rice_type, group_xmlid in RICE_TYPE_GROUP_XMLIDS.items()
            if self.env.user.has_group(group_xmlid)
        ]
        # Exactly one group membership = locked to that rice type.
        return memberships[0] if len(memberships) == 1 else ''

    def _get_rice_type_label(self, rice_type: str) -> str:
        """Human-readable label for error messages."""
        labels = dict(self._fields['rice_type']._description_selection(self.env))
        return labels.get(rice_type, rice_type)

    # ==========================================================
    # UI SUPPORT
    # ==========================================================

    @api.depends_context('uid')
    def _compute_is_rice_type_locked(self) -> None:
        locked = bool(self._get_user_rice_type())
        for rec in self:
            rec.is_rice_type_locked = locked

    # ==========================================================
    # ENFORCEMENT (server-side: the real lock - view readonly is cosmetic)
    # ==========================================================

    @api.model
    def default_get(self, fields_list: List[str]) -> Dict[str, Any]:
        """A restricted user's new PRS starts on their own rice type."""
        defaults = super().default_get(fields_list)
        user_rice_type = self._get_user_rice_type()
        if user_rice_type and 'rice_type' in fields_list:
            defaults['rice_type'] = user_rice_type
        return defaults

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'ProcessRiceSpec':
        """Restricted users can only create PRS of their own rice type -
        enforced on the server, so imports and API calls are covered too.
        (Duplicate is covered as well: copy routes through create.)"""
        user_rice_type = self._get_user_rice_type()
        if user_rice_type:
            for vals in vals_list:
                provided_type = vals.get('rice_type')
                if provided_type and provided_type != user_rice_type:
                    raise UserError(_(
                        "Your user is restricted to %(user_type)s: you cannot create a "
                        "%(provided)s Process Rice Specification.",
                        user_type=self._get_rice_type_label(user_rice_type),
                        provided=self._get_rice_type_label(provided_type),
                    ))
                vals['rice_type'] = user_rice_type
        return super().create(vals_list)

    def write(self, vals: Dict[str, Any]) -> bool:
        """Restricted users cannot CHANGE the rice type on any record.
        (Writing the same value back is allowed, so ordinary edits of other
        fields never trip the guard.)"""
        if 'rice_type' in vals:
            user_rice_type = self._get_user_rice_type()
            if user_rice_type:
                for rec in self:
                    if vals['rice_type'] != rec.rice_type:
                        raise UserError(_(
                            "Your user is restricted to %(user_type)s: you cannot change "
                            "the Rice Type of '%(record)s'.",
                            user_type=self._get_rice_type_label(user_rice_type),
                            record=rec.display_name,
                        ))
        return super().write(vals)
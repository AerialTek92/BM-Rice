# -*- coding: utf-8 -*-

from odoo import models, fields, api
from typing import Dict, Any, List


class ProductAllowanceType(models.Model):
    _name = 'product.allowance.type'
    _description = 'Master Allowance Types'

    name = fields.Char(string="Allowance Name", required=True)
    code = fields.Char(string="Allowance Code", required=True)

    template_line_ids = fields.One2many(
        'product.allowance.type.line',
        'allowance_type_id',
        string="Allowance Lines"
    )


class ProductAllowanceTemplateLine(models.Model):
    _name = 'product.allowance.type.line'
    _description = 'Allowance Lines'

    allowance_type_id = fields.Many2one('product.allowance.type', ondelete='cascade')
    rate_per_kg = fields.Float(string="Rate Per Kg")
    from_pct = fields.Float(string="From %")
    to_pct = fields.Float(string="To %")
    from_date = fields.Date(string="From Date")
    to_date = fields.Date(string="To Date")


class BrownRiceSpecification(models.Model):
    _name = 'brown.rice.specification'
    _description = 'Brown Rice Specification'

    name = fields.Char(string='Name', required=True)

    # Left Column Fields (As per SS)
    purity = fields.Float(string='Purity')
    broken = fields.Float(string='Broken')
    green_grains = fields.Float(string='Green grains')
    chalky_grains = fields.Float(string='Chalky grains')
    red_grains = fields.Float(string='Red grains')
    paddy_grains = fields.Float(string='Paddy grains')
    immature_shriveled = fields.Float(string='Immature & Shriveled')
    foreign_matter = fields.Float(string='Foreign Matter')
    damaged_yellow = fields.Float(string='Damaged & Yellow')

    # Right Column Fields (As per SS)
    insect_damage = fields.Float(string='Insect Damage')
    filth_extraneous = fields.Float(string='Filth & extraneous matter')
    aflatoxins = fields.Float(string='Aflatoxins B1+B2+G1+G2')
    mouth_babes = fields.Float(string='Mouth / Babes')
    living_insects_mites = fields.Float(string='Living insects & mites')
    moisture = fields.Float(string='Moisture')
    polish = fields.Char(string='Polish')
    avg_grain_length = fields.Float(string='Av. Grain Length')


# ==========================================
# PER-PRODUCT SPECIFICATION LINES
# Exactly the PRS normal-spec field set, one line per spec row.
# The Specification tab is mutually exclusive with the Brown Rice tab
# (is_specification / is_brown_rice checkboxes untick each other).
# ==========================================
class ProductSpecificationLine(models.Model):
    _name = 'product.specification.line'
    _description = 'Product Specification'
    _order = 'id asc'

    product_tmpl_id = fields.Many2one(
        'product.template', string='Product', required=True, ondelete='cascade')

    # --- Normal Rice Specs (mirrors PRS n_* fields, same names/types) ---
    n_moisture_percent = fields.Float(string='Moisture (%)')
    n_broken_percent = fields.Float(string='Broken (%)')
    n_damaged_discolor_percent = fields.Float(string='Damage/Discolor (%)')
    n_foreign_matter_percent = fields.Float(string='Foreign Matter (%)')
    n_paddy_percent = fields.Char(string='Paddy Grain/Kg')
    n_red_percent = fields.Float(string='Red (%)')
    n_chalky_percent = fields.Float(string='Chalky (%)')
    n_immature = fields.Float(string='Immature')
    n_cooking = fields.Char(string='Cooking', default="null")
    n_insect_damage_grains = fields.Float(string='Insect Damage Grains (%)')
    n_foreign_food_grains = fields.Float(string='Foreign Food Grains (%)')
    n_under_milled_grains = fields.Float(string='Under-milled Grains (%)')
    n_contrasting_varieties = fields.Float(string='Contrasting Varieties (%)')
    n_living_insects_mites = fields.Char(string='Living Insects & Mites')
    n_polish = fields.Char(string='Polish')
    n_agl = fields.Float(string='AGL (mm)')
    n_kett_whiteness = fields.Float(string='KETT Whiteness')


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    allowance_type_ids = fields.Many2many('product.allowance.type', string="Allowance Types")

    # Brown Rice Fields (is_brown_rice still read by the Sales Contract
    # line onchange - kept and functional on the Brown Rice tab).
    is_brown_rice = fields.Boolean(string='Brown Rice')
    brown_rice_spec_id = fields.Many2one('brown.rice.specification', string='Brown Rice Specs')

    # Product categorization: Specification tab vs Brown Rice tab.
    is_specification = fields.Boolean(string='Specification')

    # By Product Field
    is_by_product = fields.Boolean(string='By Product')

    # Packaging Configuration
    piece_weight = fields.Float(
        string='Weight per Piece (kg)',
        default=1.0,
        help="Weight of a single piece in kg. E.g., if 1 piece is 5kg, enter 5."
    )
    carton_capacity = fields.Integer(
        string='Pieces per Carton',
        default=1,
        help="Number of pieces that fit inside one carton. E.g., if 10 pieces make a carton, enter 10."
    )

    additional_weight = fields.Float(
        string='Additional Weight (g/kg)',
        default=0.0,
        help="Additional weight in grams per kg of product. E.g., 2g per kg."
    )

    # Per-product Specifications (one line per spec row)
    specification_line_ids = fields.One2many(
        'product.specification.line',
        'product_tmpl_id',
        string='Specifications',
    )

    @api.onchange('is_specification')
    def _onchange_is_specification(self) -> None:
        """Checking Specification unticks Brown Rice (mutual exclusion)."""
        if self.is_specification:
            self.is_brown_rice = False

    @api.onchange('is_brown_rice')
    def _onchange_is_brown_rice(self) -> None:
        """Checking Brown Rice unticks Specification (mutual exclusion)."""
        if self.is_brown_rice:
            self.is_specification = False
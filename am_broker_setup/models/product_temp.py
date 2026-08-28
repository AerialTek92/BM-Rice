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


# ==========================================
# NEW MODEL FOR BROWN RICE SPECIFICATIONS
# ==========================================
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


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    allowance_type_ids = fields.Many2many('product.allowance.type', string="Allowance Types")

    # NEW: Brown Rice Fields
    is_brown_rice = fields.Boolean(string='Brown Rice')
    brown_rice_spec_id = fields.Many2one('brown.rice.specification', string='Brown Rice Specs')

    # NEW: By Product Field
    is_by_product = fields.Boolean(string='By Product')

    # NEW: Packaging Configuration
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
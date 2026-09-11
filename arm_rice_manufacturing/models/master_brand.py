# -*- coding: utf-8 -*-

from odoo import models, fields


class MasterBrand(models.Model):
    _name = 'master.brand'
    _description = 'Master Brand'
    _order = 'name asc'

    name = fields.Char(string='Brand Name', required=True)
    active = fields.Boolean(string='Active', default=True,
                            help="Archived brands disappear from selections but keep their history.")
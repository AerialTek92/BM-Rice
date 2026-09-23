# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from typing import Any, Dict, List, Tuple

COMMAND_CLEAR_ALL: Tuple[int, int, int] = (5, 0, 0)
COMMAND_CREATE_NEW: int = 0

IRRI_RICE_TYPE: str = 'irri'
GRAMS_TO_KG_DIVISOR: float = 1000.0
LBS_TO_KG_FACTOR: float = 0.453592

PACKING_LINE_SYNC_FIELDS: Tuple[str, ...] = (
    'brand_id', 'process_rice_qty', 'empty_bag_to_be_shipped', 'packing', 'pp_bag_uom', 'pp_bag_kg',
    'pp_bag_lb', 'pp_bags_kgs', 'no_of_bags', 'empty_bag_weight',
)


class BrandJobOrder(models.Model):
    _name = 'brand.job.order'
    _description = 'Brand Job Order'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'smart.button.mixin', 'approval.tracker.mixin']
    _order = 'id desc'

    name = fields.Char(string='Job Order No.', index=True, readonly=True, copy=False, default=lambda self: _('New'))
    date = fields.Date(string='Job Date', default=fields.Date.today(), required=True)

    process_rice_spec_id = fields.Many2one('process.rice.spec', string='Specification No.')

    prs_contract_id = fields.Many2one(
        'rice.sales.contract',
        related='process_rice_spec_id.rice_sales_contract_id',
        store=False
    )

    rice_sales_contract_id = fields.Many2one('rice.sales.contract', string='Sales Contract')
    partner_id = fields.Many2one('res.partner', string='Customer')
    rice_type = fields.Selection(related='process_rice_spec_id.rice_type', string='Rice Type', store=True,
                                 readonly=True)

    product_id = fields.Many2one('product.product', string='Process Rice')

    process_rice_ids = fields.Many2many(
        'product.product',
        'bjo_process_rice_rel',
        'job_order_id',
        'product_id',
        string='Process Rice',
        help="IRRI only: all Process Rice products produced under this Job Order. "
             "Every product enters stock with its own weighed quantity.",
    )

    # NEW FIELD: Unified display for List View
    display_process_rice = fields.Char(
        string='Process Rice',
        compute='_compute_display_process_rice',
        store=True
    )

    brand_id = fields.Many2one('master.brand', string='Brand')
    brand_ids = fields.Many2many(
        'master.brand',
        'bjo_brand_rel',
        'job_order_id',
        'brand_id',
        string='Brand',
        help="IRRI only: all Brands produced under this Job Order.",
    )

    raw_rice_ids = fields.Many2many('product.product', string='Raw Rice', readonly=True)
    process_rice_qty = fields.Float(string='Process Rice QTY')
    quantity_mt = fields.Float(string='Quantity [MT]')
    contract_date = fields.Date(string='Contract Date')

    destination_country = fields.Many2one('res.country', string='Destination Country')

    shipment_period = fields.Char(string='Shipment Period')
    broken_percent = fields.Float(string='Broken (%)')
    moisture_percent = fields.Float(string='Moisture (%)')

    packing_line_ids = fields.One2many(
        'brand.job.order.packing.line',
        'job_order_id',
        string='Packing Lines',
    )

    packing = fields.Selection([
        ('pp_bags', 'PP Bags'),
        ('bo_pp_bags', 'BO PP Bags'),
        ('jute_bags', 'Jute Bags'),
        ('laminated', 'Laminated'),
        ('non_woven_bags', 'Non Woven Bags'),
        ('china_cotton', 'China Cotton')
    ], string='Packing', compute='_compute_packing_mirrors', store=True)

    pp_bag_uom = fields.Selection([
        ('kg', 'Kgs'),
        ('lb', 'Lbs')
    ], string='Unit of Measure', compute='_compute_packing_mirrors', store=True)

    pp_bag_kg = fields.Many2one(
        'master.bag.weight',
        string='Weight (Kgs)',
        compute='_compute_packing_mirrors',
        store=True,
    )

    pp_bag_lb = fields.Float(string='Weight (Lbs)', compute='_compute_packing_mirrors', store=True)
    pp_bags_kgs = fields.Float(string='PP Bags (Kgs)', compute='_compute_packing_mirrors', store=True)

    no_of_bags = fields.Integer(
        string='No of Bags',
        compute='_compute_no_of_bags',
        store=True,
        readonly=False,
        help="Auto-calculated as Planned Qty / bag weight, editable for manual correction.",
    )
    empty_bag_weight = fields.Float(string='Empty Bag Weight (gram)', compute='_compute_packing_mirrors', store=True)

    total_empty_bag_weight = fields.Float(
        string='Total Empty Bag Weight (grams)',
        compute='_compute_packing_mirrors',
        store=True,
    )
    net_weight = fields.Float(string='Net Weight', compute='_compute_packing_mirrors', store=True)
    gross_weight = fields.Float(string='Gross Weight', compute='_compute_packing_mirrors', store=True)

    fumigation_chemical = fields.Selection([
        ('aluminum_phosphide', 'Aluminum Phosphide'),
        ('methyl_bromide', 'Methyl Bromide')
    ], string='Chemical Advised', default='aluminum_phosphide')

    fumigation_method = fields.Char(string='Dosage')

    phyto_certificate_req = fields.Selection([
        ('yes', 'Yes'),
        ('no', 'No')
    ], string='Phyto Certificate Requirement', default='no')

    fumigation_agency_id = fields.Many2one(
        'fumigation.agency',
        string='Fumigation Agency',
    )
    no_of_samples = fields.Integer(string='No Of Samples Required')
    inspection_agency = fields.Many2one(
        'inspection.agency',
        string='Inspection Agency',
    )
    inspection_date = fields.Date(string='Inspection Date')
    remarks = fields.Html(string='Remarks')

    state = fields.Selection([
        ('draft', 'Draft'), ('confirmed', 'Confirmed'), ('in_progress', 'In Progress'), ('done', 'Done'),
        ('cancel', 'Cancelled')
    ], string='Status', default='draft', tracking=True)

    issue_material_count = fields.Integer(string='Issue Materials', compute='_compute_issue_material_count')
    production_record_count = fields.Integer(string='Productions', compute='_compute_production_record_count')

    @api.depends('product_id', 'process_rice_ids', 'rice_type')
    def _compute_display_process_rice(self):
        """Unified display for both IRRI (Tags/Names) and Basmati (Single Name)."""
        for rec in self:
            if rec.rice_type == IRRI_RICE_TYPE and rec.process_rice_ids:
                rec.display_process_rice = ", ".join(rec.process_rice_ids.mapped('name'))
            elif rec.product_id:
                rec.display_process_rice = rec.product_id.name
            else:
                rec.display_process_rice = ""

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'BrandJobOrder':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('brand.job.order') or _('New')

        orders = super().create(vals_list)

        for order in orders:
            if order.rice_type == IRRI_RICE_TYPE:
                order.product_id = order._get_derived_process_rice()
            if not order.packing_line_ids:
                order._sync_packing_lines_to_products()

        for order in orders:
            matrix = order._apply_default_approval_matrix()
            if matrix:
                line_vals = []
                for m_line in matrix.line_ids:
                    line_vals.append((COMMAND_CREATE_NEW, 0, {
                        'res_model': order._name,
                        'res_id': order.id,
                        'sequence': m_line.sequence,
                        'label': m_line.label,
                        'employee_id': m_line.employee_id.id if m_line.employee_id else False,
                        'group_id': m_line.group_id.id if m_line.group_id else False,
                        'matrix_line_id': m_line.id,
                        'status': 'waiting',
                    }))
                if line_vals:
                    order.approval_line_ids = line_vals
        return orders

    @api.depends(
        'process_rice_spec_id.pp_bag_uom',
        'packing_line_ids.brand_id',
        'packing_line_ids.packing', 'packing_line_ids.pp_bag_uom',
        'packing_line_ids.pp_bag_kg', 'packing_line_ids.pp_bag_lb',
        'packing_line_ids.pp_bags_kgs', 'packing_line_ids.empty_bag_weight',
        'packing_line_ids.no_of_bags', 'packing_line_ids.gross_weight',
    )
    def _compute_packing_mirrors(self) -> None:
        for rec in self:
            spec_uom = rec.process_rice_spec_id.pp_bag_uom
            first_line = rec.packing_line_ids[:1]
            rec.packing = first_line.packing
            rec.pp_bag_uom = spec_uom or first_line.pp_bag_uom
            rec.pp_bag_kg = first_line.pp_bag_kg
            rec.pp_bag_lb = first_line.pp_bag_lb
            rec.pp_bags_kgs = first_line.pp_bags_kgs
            rec.empty_bag_weight = first_line.empty_bag_weight
            rec.no_of_bags = sum(rec.packing_line_ids.mapped('no_of_bags'))

            total_tare_grams = sum(
                (line.empty_bag_weight or 0.0) * (line.no_of_bags or 0)
                for line in rec.packing_line_ids
            )
            rec.total_empty_bag_weight = total_tare_grams

            gross_total = sum(rec.packing_line_ids.mapped('gross_weight'))
            rec.gross_weight = gross_total
            rec.net_weight = (gross_total - total_tare_grams / GRAMS_TO_KG_DIVISOR) if gross_total > 0 else 0.0

    @api.depends('process_rice_qty', 'pp_bags_kgs')
    def _compute_no_of_bags(self) -> None:
        for line in self:
            if line.process_rice_qty > 0 and line.pp_bags_kgs > 0:
                line.no_of_bags = int(line.process_rice_qty / line.pp_bags_kgs)
            else:
                line.no_of_bags = 0

    @api.depends('name', 'partner_id.name', 'quantity_mt', 'product_id.name')
    def _compute_display_name(self) -> None:
        if self.env.context.get('production_record_job_view'):
            for order in self:
                partner_name = order.partner_id.name or ''
                qty = order.quantity_mt or 0.0
                brand_name = order.product_id.name or ''
                order.display_name = f"{order.name or ''} | {partner_name} | {qty} | {brand_name}"
        else:
            super()._compute_display_name()

    def _compute_issue_material_count(self) -> None:
        counts = self._get_related_record_count_batch('issue.material', 'job_order_id')
        for rec in self:
            rec.issue_material_count = counts.get(rec.id, 0)

    def _compute_production_record_count(self) -> None:
        counts = self._get_related_record_count_batch('production.record', 'job_order_id')
        for rec in self:
            rec.production_record_count = counts.get(rec.id, 0)

    def _get_derived_process_rice(self) -> 'product.product':
        self.ensure_one()
        return self.process_rice_ids.sorted(key=lambda product: product.name or '')[:1]

    def _get_job_process_rice_products(self) -> 'product.product':
        self.ensure_one()
        if self.rice_type == IRRI_RICE_TYPE:
            return self.process_rice_ids
        return self.product_id or self.env['product.product']

    def _get_job_brands(self) -> 'master.brand':
        self.ensure_one()
        if self.rice_type == IRRI_RICE_TYPE:
            return self.brand_ids
        return self.brand_id or self.env['master.brand']

    @api.onchange('process_rice_ids')
    def _onchange_process_rice_ids_sync_product(self) -> None:
        if self.rice_type == IRRI_RICE_TYPE:
            self.product_id = self._get_derived_process_rice()

    def _map_brands_to_lines(self, commands: List[Tuple[int, int, Dict[str, Any]]]) -> None:
        self.ensure_one()
        brands = self._get_job_brands()
        if not brands:
            return
        next_brand_index = 0
        for command in commands:
            if command[0] != COMMAND_CREATE_NEW:
                continue
            line_vals = command[2]
            if line_vals.get('brand_id'):
                continue
            line_vals['brand_id'] = brands[next_brand_index % len(brands)].id
            next_brand_index += 1

    def _sync_packing_lines_to_products(self) -> None:
        self.ensure_one()
        products = self._get_job_process_rice_products()
        existing_map: Dict[int, Dict[str, Any]] = {}
        for line in self.packing_line_ids:
            if line.product_id and line.product_id in products:
                line_vals = {'product_id': line.product_id.id}
                for field_name in PACKING_LINE_SYNC_FIELDS:
                    line_vals[field_name] = line[field_name]
                existing_map[line.product_id.id] = line_vals
        commands: List[Tuple[int, int, Dict[str, Any]]] = [COMMAND_CLEAR_ALL]
        for product in products:
            if product.id in existing_map:
                commands.append((COMMAND_CREATE_NEW, 0, existing_map[product.id]))
            else:
                commands.append((COMMAND_CREATE_NEW, 0, {'product_id': product.id}))
        self._map_brands_to_lines(commands)
        self.packing_line_ids = commands

    @api.onchange('process_rice_ids', 'product_id')
    def _onchange_process_rice_sync_packing_lines(self) -> None:
        self._sync_packing_lines_to_products()

    @api.onchange('brand_ids', 'brand_id')
    def _onchange_brand_sync_packing_lines(self) -> None:
        self.ensure_one()
        brands = self._get_job_brands()
        self.packing_line_ids = [
                                    (COMMAND_CLEAR_ALL, 0, 0),
                                ] + [
                                    (COMMAND_CREATE_NEW, 0, {
                                        'product_id': line.product_id.id,
                                        **{field_name: line[field_name] for field_name in PACKING_LINE_SYNC_FIELDS},
                                    })
                                    for line in self.packing_line_ids
                                    if line.brand_id in brands or not line.brand_id
                                ]
        rebuilt_commands = self.packing_line_ids[1:]
        next_brand_index = 0
        for command in rebuilt_commands:
            if command[0] != COMMAND_CREATE_NEW:
                continue
            line_vals = command[2]
            if line_vals.get('brand_id') and line_vals['brand_id'] in brands.ids:
                continue
            line_vals['brand_id'] = brands[next_brand_index % len(brands)].id if brands else False
            next_brand_index += 1

    @api.onchange('process_rice_spec_id')
    def _onchange_process_rice_spec_id(self) -> None:
        if not self.process_rice_spec_id:
            self.update({
                'rice_sales_contract_id': False, 'partner_id': False, 'product_id': False,
                'process_rice_ids': [(5, 0, 0)],
                'brand_id': False, 'brand_ids': [(5, 0, 0)],
                'raw_rice_ids': [(5, 0, 0)],
                'quantity_mt': 0.0, 'contract_date': False,
                'destination_country': False, 'shipment_period': False, 'broken_percent': 0.0,
                'moisture_percent': 0.0, 'inspection_agency': False,
                'remarks': False,
            })
            self.packing_line_ids = [COMMAND_CLEAR_ALL]
            return
        prs = self.process_rice_spec_id
        rsc = prs.rice_sales_contract_id
        shipment_period = False
        if rsc and rsc.delivery_date_from and rsc.delivery_date_to:
            shipment_period = f"{rsc.delivery_date_from.strftime('%d/%m/%Y')} to {rsc.delivery_date_to.strftime('%d/%m/%Y')}"
        bjo_remarks = ""
        if prs.remarks:
            bjo_remarks = f"<b>Process Rice Spec Remarks:</b><br/>{prs.remarks}<br/><br/><b>Brand Job Order Remarks:</b><br/>"
        else:
            bjo_remarks = "<b>Brand Job Order Remarks:</b><br/>"
        raw_product_ids = prs.spec_line_ids.mapped('product_id').ids
        destination_country_val = prs.destination_country_id.id
        if not destination_country_val and rsc and rsc.destination_country_id:
            destination_country_val = rsc.destination_country_id.id
        self.update({
            'rice_sales_contract_id': rsc.id if rsc else False,
            'partner_id': prs.partner_id.id,
            'product_id': prs.product_id.id,
            'process_rice_ids': [(6, 0, prs.process_rice_ids.ids)],
            'brand_id': prs.brand_id.id,
            'brand_ids': [(6, 0, prs.brand_ids.ids)],
            'raw_rice_ids': [(6, 0, raw_product_ids)],
            'quantity_mt': sum(prs.spec_line_ids.mapped('quantity')),
            'process_rice_qty': prs.process_rice_qty,
            'contract_date': rsc.contract_date if rsc else False,
            'destination_country': destination_country_val,
            'shipment_period': shipment_period,
            'broken_percent': prs.n_broken_percent,
            'moisture_percent': prs.n_moisture_percent,
            'inspection_agency': rsc.inspection_agency if rsc else False,
            'remarks': bjo_remarks,
        })
        prs_products = prs.process_rice_ids | prs.product_id
        prs_brands = prs.brand_ids | prs.brand_id
        qty_map = {line.product_id.id: line.qty_mt for line in prs.process_rice_line_ids}
        packing_commands: List[Tuple[int, int, Dict[str, Any]]] = [COMMAND_CLEAR_ALL]
        for brand_index, product in enumerate(prs_products):
            brand_val = prs_brands[brand_index % len(prs_brands)].id if prs_brands else False
            packing_commands.append((COMMAND_CREATE_NEW, 0, {
                'product_id': product.id,
                'brand_id': brand_val,
                'process_rice_qty': qty_map.get(product.id, 0.0),
                'packing': prs.packing,
                'pp_bag_uom': prs.pp_bag_uom,
                'pp_bag_kg': prs.pp_bag_kg.id,
                'pp_bag_lb': prs.pp_bag_lb,
            }))
        self.packing_line_ids = packing_commands

    def action_confirm(self) -> None:
        for rec in self:
            is_admin = self.env.user.has_group('base.group_system')
            if rec.approval_line_ids and rec.approval_status != 'approved' and not is_admin:
                raise UserError(_("You cannot confirm this Job Order until all approvals are completed."))
            if rec.rice_type == IRRI_RICE_TYPE:
                if not rec.process_rice_ids:
                    raise UserError(_("Please select at least one Process Rice product before confirming."))
            elif not rec.product_id:
                raise UserError(_("Please specify a Process Rice product before confirming."))
            rec.state = 'confirmed'

    def _execute_post_approval(self):
        self.ensure_one()
        if self.state == 'draft':
            self.action_confirm()

    def action_cancel(self) -> None:
        for rec in self:
            if rec.state in ('done', 'cancel'):
                raise UserError(_("A Job Order in state '%(state)s' cannot be cancelled.", state=rec.state))
            rec.state = 'cancel'

    def action_reset_to_draft(self) -> None:
        for rec in self:
            if rec.state != 'cancel':
                raise UserError(_("Only a Cancelled Job Order can be reset to draft. Current state: %s.", rec.state))
            rec.state = 'draft'

    def action_create_planning_sheet(self) -> Dict[str, Any]:
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Production Planning',
            'res_model': 'production.planning',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_job_order_id': self.id,
                'default_date': fields.Date.today(),
            }
        }

    def _get_open_related_document(self, model_name: str) -> int:
        self.ensure_one()
        existing = self.env[model_name].search([
            ('job_order_id', '=', self.id),
            ('state', '=', 'draft')
        ], limit=1)
        return existing.id or False

    def _has_confirmed_related_documents(self, model_name: str) -> bool:
        self.ensure_one()
        return bool(self.env[model_name].search_count([
            ('job_order_id', '=', self.id),
            ('state', 'not in', ('draft', 'cancel'))
        ]))

    def _prepare_child_document_action(self, model_name: str, display_name: str,
                                       context_defaults: Dict[str, Any]) -> Dict[str, Any]:
        self.ensure_one()
        open_document_id = self._get_open_related_document(model_name)
        if open_document_id:
            return self._open_form_view(model_name, open_document_id, display_name)
        context_vals = dict(context_defaults)
        if self._has_confirmed_related_documents(model_name):
            context_vals['default_is_reworking'] = True
        return {
            'type': 'ir.actions.act_window',
            'name': display_name,
            'res_model': model_name,
            'view_mode': 'form',
            'target': 'current',
            'context': context_vals,
        }

    def action_create_issue_material(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._prepare_child_document_action(
            'issue.material', 'Issue Material',
            {
                'default_job_order_id': self.id,
                'default_issue_date': fields.Date.today(),
            }
        )

    def action_view_issue_materials(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_related_records('issue.material', 'job_order_id', 'Issue Material')

    def action_create_production_record(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._prepare_child_document_action(
            'production.record', 'Rice Recovery',
            {
                'default_job_order_id': self.id,
                'default_production_date': fields.Date.today(),
            }
        )

    def action_view_production_records(self) -> Dict[str, Any]:
        self.ensure_one()
        return self._open_related_records('production.record', 'job_order_id', 'Rice Recovery')

    def _apply_default_approval_matrix(self):
        self.ensure_one()
        matrix = self.env['approval.matrix'].sudo().search([
            ('model_id.model', '=', self._name),
            ('rice_type', '=', self.rice_type)
        ], limit=1)
        if not matrix:
            matrix = self.env['approval.matrix'].sudo().search([
                ('model_id.model', '=', self._name),
                ('rice_type', '=', 'all')
            ], limit=1)
        return matrix


class BrandJobOrderPackingLine(models.Model):
    _name = 'brand.job.order.packing.line'
    _description = 'Brand Job Order Packing Line'
    _order = 'id asc'

    job_order_id = fields.Many2one('brand.job.order', string='Job Order', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Process Rice', required=True)
    brand_id = fields.Many2one('master.brand', string='Brand')
    process_rice_qty = fields.Float(string='Planned Qty (MT)')
    empty_bag_to_be_shipped = fields.Float(string='Empty Bag to be Shipped (%)')
    packing = fields.Selection([
        ('pp_bags', 'PP Bags'),
        ('bo_pp_bags', 'BO PP Bags'),
        ('jute_bags', 'Jute Bags'),
        ('laminated', 'Laminated'),
        ('non_woven_bags', 'Non Woven Bags'),
        ('china_cotton', 'China Cotton')
    ], string='Packing')
    pp_bag_uom = fields.Selection(
        [('kg', 'Kgs'), ('lb', 'Lbs')],
        string='Unit of Measure',
        compute='_compute_pp_bag_uom',
        store=True,
        readonly=True,
    )
    pp_bag_kg = fields.Many2one('master.bag.weight', string='Weight (Kgs)')
    pp_bag_lb = fields.Float(string='Weight (Lbs)')
    pp_bags_kgs = fields.Float(string='PP Bags (Kg)', compute='_compute_pp_bags_kgs', store=True)
    no_of_bags = fields.Integer(string='No of Bags')
    empty_bag_weight = fields.Integer(string='Empty Bag Weight (Grams)')
    gross_weight = fields.Float(
        string='Gross Weight (Kg)',
        compute='_compute_gross_weight',
        store=True,
        readonly=True,
    )

    @api.depends('job_order_id.process_rice_spec_id.pp_bag_uom')
    def _compute_pp_bag_uom(self) -> None:
        for line in self:
            spec_uom = line.job_order_id.process_rice_spec_id.pp_bag_uom
            line.pp_bag_uom = spec_uom or 'kg'

    @api.depends('pp_bag_uom', 'pp_bag_kg', 'pp_bag_lb')
    def _compute_pp_bags_kgs(self) -> None:
        for line in self:
            if line.pp_bag_uom == 'kg':
                line.pp_bags_kgs = line.pp_bag_kg.weight_kg if line.pp_bag_kg else 0.0
            else:
                line.pp_bags_kgs = line.pp_bag_lb or 0.0

    def _get_gross_weight_value(self) -> float:
        spec_uom = self.job_order_id.process_rice_spec_id.pp_bag_uom or self.pp_bag_uom
        if spec_uom == 'lb':
            bag_weight_kg = (self.pp_bag_lb or 0.0) * LBS_TO_KG_FACTOR
        else:
            bag_weight_kg = self.pp_bag_kg.weight_kg if self.pp_bag_kg else 0.0
        tare_kg = (self.empty_bag_weight or 0.0) / GRAMS_TO_KG_DIVISOR
        return round(tare_kg + bag_weight_kg, 3)

    @api.depends('job_order_id.process_rice_spec_id.pp_bag_uom',
                 'pp_bag_kg', 'pp_bag_lb', 'empty_bag_weight')
    def _compute_gross_weight(self) -> None:
        for line in self:
            line.gross_weight = line._get_gross_weight_value()

    @api.onchange('pp_bag_kg', 'pp_bag_lb', 'empty_bag_weight', 'pp_bag_uom')
    def _onchange_packing_inputs_update_gross(self) -> None:
        for line in self:
            line.gross_weight = line._get_gross_weight_value()


class FumigationAgency(models.Model):
    _name = 'fumigation.agency'
    _description = 'Fumigation Agency'
    _order = 'name'
    name = fields.Char(string='Agency Name', required=True)


class InspectionAgency(models.Model):
    _name = 'inspection.agency'
    _description = 'Inspection Agency'
    _order = 'name'
    name = fields.Char(string='Inspection Agency Name', required=True)

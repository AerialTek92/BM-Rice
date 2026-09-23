# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from typing import Dict, Any, List, Tuple

COMMAND_CLEAR_ALL: Tuple[int, int, int] = (5, 0, 0)
COMMAND_CREATE_NEW: int = 0
HOURS_PER_DAY: float = 24.0

WEEKDAY_KEYS: Tuple[str, ...] = (
    'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
)

PLANT_SELECTION_KEY_MAP: Dict[str, str] = {
    'Plant A': 'plant_a',
    'Plant B': 'plant_b',
    'Plant C': 'plant_c',
}


def _elapsed_hours(start_time: float, stop_time: float) -> float:
    difference = stop_time - start_time
    if difference < 0:
        difference += HOURS_PER_DAY
    return difference


class MasterPlant(models.Model):
    _name = 'master.plant'
    _description = 'Master Plant'
    _order = 'name asc'
    name = fields.Char(string='Plant Name', required=True)
    active = fields.Boolean(string='Active', default=True)


class ProductionLogSheet(models.Model):
    _name = 'production.log.sheet'
    _description = 'Production Log Sheet'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'smart.button.mixin']
    _order = 'id desc'

    name = fields.Char(string='Log No.', index=True, readonly=True, copy=False, default=lambda self: _('New'))

    # POINT 1: Many2many with EXPLICIT table name for migration safety
    issue_material_id = fields.Many2many(
        'issue.material',
        'production_log_issue_material_rel',  # Join Table
        'log_id',  # Column 1
        'issue_id',  # Column 2
        string='Issue Material Ref'
    )

    milling_date = fields.Date(string='Milling Date')
    show_bm1 = fields.Boolean(string="BM 1", default=True)
    show_bm2 = fields.Boolean(string="BM 2", default=False)

    bm1_plant_ids = fields.Many2many(
        'master.plant', 'pls_bm1_plant_rel', 'log_sheet_id', 'plant_id',
        string='BM-1 Plants'
    )

    bm1_plant = fields.Selection([
        ('plant_a', 'Plant A'), ('plant_b', 'Plant B'), ('plant_c', 'Plant C')
    ], string='BM-1 (legacy)', compute='_compute_bm1_plant', store=True)

    bm2_plant = fields.Selection([('plant_a', 'Plant A')], string='BM-2')
    date = fields.Date(string='Date', default=fields.Date.today(), required=True)

    day = fields.Selection([
        ('monday', 'Monday'), ('tuesday', 'Tuesday'), ('wednesday', 'Wednesday'),
        ('thursday', 'Thursday'), ('friday', 'Friday'), ('saturday', 'Saturday'), ('sunday', 'Sunday')
    ], string='Day', compute='_compute_day', store=True, readonly=False)

    shift = fields.Selection([
        ('8_hours', '8 Hours'), ('12_hours', '12 Hours'), ('24_hours', '24 Hours')
    ], string='Shift Hours', default='8_hours')

    shift_type = fields.Selection([
        ('day', 'Day Shift'), ('night', 'Night Shift (A+B)'), ('general', 'General Shift')
    ], string='Shift Type', default='day')

    operator_name = fields.Many2one('operator.name', string='Operator Name')

    customer_1_id = fields.Many2one('res.partner', string='1st Customer Name')
    job_order_1_id = fields.Many2one('brand.job.order', string='1st Job Order No.')
    customer_2_id = fields.Many2one('res.partner', string='2nd Customer Name')
    job_order_2_id = fields.Many2one('brand.job.order', string='2nd Job Order No.')

    running_line_ids = fields.One2many('production.log.running.line', 'log_sheet_id', string='Running Time')
    stop_line_ids = fields.One2many('production.log.stop.line', 'log_sheet_id', string='Stop Time')
    packing_line_ids = fields.One2many('production.log.packing.line', 'log_sheet_id', string='Final Product Packing')
    byproduct_line_ids = fields.One2many('production.log.byproduct.line', 'log_sheet_id', string='By-Product Summary')

    total_running_time = fields.Float(string='Total Running Time', compute='_compute_total_running_time', store=True,
                                      readonly=True)
    total_down_time = fields.Float(string='Total Down Time', compute='_compute_total_down_time', store=True,
                                   readonly=True)

    prepared_by = fields.Char(string='Prepared By')
    supervisor = fields.Char(string='Production Supervisor')
    production_head = fields.Char(string='Production Head')
    is_reworking = fields.Boolean(string="Reworking", default=False)
    remarks = fields.Html(string='Remarks')
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed'), ('cancel', 'Cancelled')], string='Status',
                             default='draft', tracking=True)

    # ==========================================================
    # MIGRATION LOGIC: Restore data from old Many2one field
    # ==========================================================
    # def action_migrate_old_issuance_data(self):
    #     """SQL to move data from old renamed column to new M2M table."""
    #     self.env.cr.execute("""
    #         SELECT column_name FROM information_schema.columns
    #         WHERE table_name='production_log_sheet' AND column_name LIKE 'issue_material_id%';
    #     """)
    #     cols = [row[0] for row in self.env.cr.fetchall()]
    #     old_col = next((c for c in cols if 'moved' in c or c == 'issue_material_id'), False)
    #
    #     if old_col:
    #         self.env.cr.execute(f"""
    #             INSERT INTO production_log_issue_material_rel (log_id, issue_id)
    #             SELECT id, {old_col} FROM production_log_sheet
    #             WHERE {old_col} IS NOT NULL
    #             ON CONFLICT DO NOTHING;
    #         """)
    #         return True
    #     raise UserError("Old data column not found.")

    # ==========================================================
    # TWO-WAY AUTO-SYNC LOGIC
    # ==========================================================
    @api.onchange('issue_material_id')
    def _onchange_issue_material_id(self):
        """Issuances -> Jobs"""
        if self.issue_material_id:
            jobs = self.issue_material_id.mapped('job_order_id')
            if jobs:
                self.job_order_1_id = jobs[0].id
                self.customer_1_id = jobs[0].partner_id.id
                self.milling_date = self.issue_material_id[0].milling_date
                if len(jobs) > 1:
                    self.job_order_2_id = jobs[1].id
                    self.customer_2_id = jobs[1].partner_id.id
            self._sync_all_tables_data_internal()

    @api.onchange('job_order_1_id', 'job_order_2_id')
    def _onchange_job_orders_auto_sync(self):
        """Jobs -> Issuances M2M"""
        job_ids = []
        if self.job_order_1_id:
            job_ids.append(self.job_order_1_id.id)
            self.customer_1_id = self.job_order_1_id.partner_id.id
        if self.job_order_2_id:
            job_ids.append(self.job_order_2_id.id)
            self.customer_2_id = self.job_order_2_id.partner_id.id

        if job_ids:
            issuances = self.env['issue.material'].search([('job_order_id', 'in', job_ids), ('state', '!=', 'cancel')])
            self.issue_material_id = [(6, 0, issuances.ids)]
            if issuances: self.milling_date = issuances[0].milling_date

        self._sync_all_tables_data_internal()

    def _sync_all_tables_data_internal(self):
        """Fill Running, Packing, and ByProduct tables."""
        # 1. Running Time
        new_running = [(5, 0, 0)]
        jobs_list = [(self.job_order_1_id, 'Job 1'), (self.job_order_2_id, 'Job 2')]
        for job, label in jobs_list:
            if job and job.raw_rice_ids:
                for product in job.raw_rice_ids:
                    new_running.append((0, 0, {'product_id': product.id, 'job_order_id': job.id,
                                               'remarks': f'Auto-filled from {label}'}))
        self.running_line_ids = new_running

        # 2. Packing
        process_products = self.env['product.product']
        for job, _ in jobs_list:
            if not job: continue
            if job.process_rice_ids:
                process_products |= job.process_rice_ids
            elif job.product_id:
                process_products |= job.product_id

        new_packing = [(5, 0, 0)]
        for prod in process_products:
            new_packing.append((0, 0, {'product_id': prod.id, 'variety': prod.name}))
        self.packing_line_ids = new_packing

        # 3. By-Product
        new_byproducts = [(5, 0, 0)]
        if self.job_order_1_id and self.job_order_1_id.process_rice_spec_id:
            spec = self.job_order_1_id.process_rice_spec_id
            if hasattr(spec, 'byproduct_line_ids') and spec.byproduct_line_ids:
                for b_line in spec.byproduct_line_ids:
                    new_byproducts.append((0, 0, {'product_id': b_line.product_id.id, 'size': b_line.size or 0.0}))
        self.byproduct_line_ids = new_byproducts

    # ==========================================================
    # EXISTING LOGIC PRESERVED
    # ==========================================================
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                seq_code = 'production.log.sheet.rework' if vals.get('is_reworking') else 'production.log.sheet'
                vals['name'] = self.env['ir.sequence'].next_by_code(seq_code) or _('New')
        records = super().create(vals_list)
        records._seed_stop_lines_from_running()
        return records

    def write(self, vals):
        result = super().write(vals)
        if 'running_line_ids' in vals: self._seed_stop_lines_from_running()
        return result

    def _seed_stop_lines_from_running(self):
        for log_sheet in self:
            runs = log_sheet.running_line_ids.sorted('start_time')
            if not runs: continue
            seeded_stop_times = {sl.stop_time for sl in log_sheet.stop_line_ids if sl.stop_time}
            new_stop_vals = []
            for i, run in enumerate(runs):
                if run.stop_time and run.stop_time not in seeded_stop_times:
                    next_start = runs[i + 1].start_time if (i + 1) < len(runs) else 0.0
                    new_stop_vals.append((0, 0, {'log_sheet_id': log_sheet.id, 'stop_time': run.stop_time,
                                                 'start_time': next_start, 'remarks': 'Auto-Sync'}))
            if new_stop_vals: log_sheet.write({'stop_line_ids': new_stop_vals})

    @api.depends('bm1_plant_ids.name')
    def _compute_bm1_plant(self):
        for rec in self:
            first_plant_name = rec.bm1_plant_ids[:1].name
            rec.bm1_plant = PLANT_SELECTION_KEY_MAP.get(first_plant_name or '', False)

    @api.depends('date')
    def _compute_day(self):
        for rec in self: rec.day = WEEKDAY_KEYS[rec.date.weekday()] if rec.date else 'monday'

    @api.depends('running_line_ids.actual_time')
    def _compute_total_running_time(self):
        for rec in self: rec.total_running_time = sum(rec.running_line_ids.mapped('actual_time'))

    @api.depends('stop_line_ids.down_time')
    def _compute_total_down_time(self):
        for rec in self: rec.total_down_time = sum(rec.stop_line_ids.mapped('down_time'))

    def action_confirm(self):
        for rec in self:
            if rec.state != 'draft': raise UserError(_("Only a Draft Log Sheet can be confirmed."))
            rec.state = 'confirmed'

    def action_cancel(self):
        for rec in self: rec.state = 'cancel'

    def action_reset_to_draft(self):
        for rec in self: rec.state = 'draft'

    @api.onchange('show_bm1')
    def _onchange_show_bm1(self):
        if self.show_bm1:
            self.show_bm2 = False
        else:
            self.bm1_plant_ids = [(5, 0, 0)]

    @api.onchange('show_bm2')
    def _onchange_show_bm2(self):
        if self.show_bm2:
            self.show_bm1 = False
        else:
            self.bm2_plant = False


# --- Support Line Models ---

class ProductionLogRunningLine(models.Model):
    _name = 'production.log.running.line'
    _description = 'Running Time Line'
    log_sheet_id = fields.Many2one('production.log.sheet', required=True, ondelete='cascade')
    job_order_id = fields.Many2one('brand.job.order', string='Job Order Ref', readonly=True)
    product_id = fields.Many2one('product.product', string='Item')
    start_time = fields.Float(string='Start Time')
    stop_time = fields.Float(string='Stop Time')
    actual_time = fields.Float(string='Actual Time', compute='_compute_actual_time', store=True)
    remarks = fields.Char(string='Remarks')

    @api.depends('start_time', 'stop_time')
    def _compute_actual_time(self):
        for line in self: line.actual_time = _elapsed_hours(line.start_time,
                                                            line.stop_time) if line.start_time and line.stop_time else 0.0


class ProductionLogStopLine(models.Model):
    _name = 'production.log.stop.line'
    _description = 'Stop Time Line'
    log_sheet_id = fields.Many2one('production.log.sheet', required=True, ondelete='cascade')
    stop_time = fields.Float(string='Stop Time')
    start_time = fields.Float(string='Start Time')
    down_time = fields.Float(string='Down Time', compute='_compute_down_time', store=True)
    remarks = fields.Char(string='Remarks')

    @api.depends('stop_time', 'start_time')
    def _compute_down_time(self):
        for line in self: line.down_time = _elapsed_hours(line.stop_time,
                                                          line.start_time) if line.stop_time and line.start_time else 0.0


class ProductionLogPackingLine(models.Model):
    _name = 'production.log.packing.line'
    _description = 'Packing Line'
    log_sheet_id = fields.Many2one('production.log.sheet', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Brand')
    variety = fields.Char(string='Variety')
    brand_manual = fields.Char(string='Brand (Manual)')
    no_of_bags = fields.Integer(string='No. Bags')
    packing_size = fields.Float(string='Packing Size')
    total_weight = fields.Float(string='T. Wt (MT)', compute='_compute_total_weight', store=True)
    percent = fields.Float(string='%')

    @api.depends('no_of_bags', 'packing_size')
    def _compute_total_weight(self):
        for line in self: line.total_weight = ((line.no_of_bags or 0) * (line.packing_size or 0.0)) / 1000.0


class ProductionLogByproductLine(models.Model):
    _name = 'production.log.byproduct.line'
    _description = 'By-Product Line'
    log_sheet_id = fields.Many2one('production.log.sheet', ondelete='cascade')
    wb_ticket_id = fields.Many2one('weighbridge.ticket', string='Weighbridge Ticket', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Item')
    bags = fields.Integer(string='Bags')
    size = fields.Float(string='Size')
    weight = fields.Float(string='Weight (MT)', compute='_compute_weight', store=True)
    percent = fields.Float(string='%')

    @api.depends('bags', 'size')
    def _compute_weight(self):
        for line in self: line.weight = ((line.bags or 0) * (line.size or 0.0)) / 1000.0


class OperatorName(models.Model):
    _name = 'operator.name'
    _description = 'Operator Name'
    name = fields.Char(string='Operator Name', required=True)
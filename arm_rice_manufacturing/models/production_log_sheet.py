# # -*- coding: utf-8 -*-
#
# from odoo import models, fields, api, _
# from odoo.exceptions import UserError, ValidationError
# from typing import Dict, Any, List, Tuple
#
# COMMAND_CLEAR_ALL: Tuple[int, int, int] = (5, 0, 0)
# COMMAND_CREATE_NEW: int = 0
#
# HOURS_PER_DAY: float = 24.0
#
# WEEKDAY_KEYS: Tuple[str, ...] = (
#     'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
# )
#
# # Machinery mapping: master.plant record name -> legacy selection key
# PLANT_SELECTION_KEY_MAP: Dict[str, str] = {
#     'Plant A': 'plant_a',
#     'Plant B': 'plant_b',
#     'Plant C': 'plant_c',
# }
#
#
# def _elapsed_hours(start_time: float, stop_time: float) -> float:
#     """Duration between two time-of-day values (float hours).
#     A negative difference means the period crossed midnight (night shift)."""
#     difference = stop_time - start_time
#     if difference < 0:
#         difference += HOURS_PER_DAY
#     return difference
#
#
# class MasterPlant(models.Model):
#     _name = 'master.plant'
#     _description = 'Master Plant'
#     _order = 'name asc'
#
#     name = fields.Char(string='Plant Name', required=True)
#     active = fields.Boolean(string='Active', default=True,
#                             help="Archived plants disappear from selections but keep their history.")
#
#
# class ProductionLogSheet(models.Model):
#     _name = 'production.log.sheet'
#     _description = 'Production Log Sheet'
#     _inherit = ['mail.thread', 'mail.activity.mixin', 'smart.button.mixin']
#     _order = 'id desc'
#
#     name = fields.Char(string='Log No.', index=True, readonly=True, copy=False, default=lambda self: _('New'))
#
#     issue_material_id = fields.Many2one('issue.material', string='Issue Material Ref', ondelete='restrict')
#     milling_date = fields.Date(string='Milling Date')
#
#     show_bm1 = fields.Boolean(string="BM 1", default=True)
#     show_bm2 = fields.Boolean(string="BM 2", default=False)
#
#     # MULTI-SELECT: the BM-1 plants, as tags on the master. The selection
#     # field below is MACHINERY (derived from the first tag) for downstream
#     # compatibility.
#     bm1_plant_ids = fields.Many2many(
#         'master.plant',
#         'pls_bm1_plant_rel',
#         'log_sheet_id',
#         'plant_id',
#         string='BM-1 Plants',
#         help="The BM-1 plants this shift ran on. Select multiple when the shift covered several plants.",
#     )
#
#     bm1_plant = fields.Selection([
#         ('plant_a', 'Plant A'),
#         ('plant_b', 'Plant B'),
#         ('plant_c', 'Plant C')
#     ], string='BM-1 (legacy)', compute='_compute_bm1_plant', store=True)
#
#     bm2_plant = fields.Selection([
#         ('plant_a', 'Plant A')
#     ], string='BM-2')
#
#     date = fields.Date(string='Date', default=fields.Date.today(), required=True)
#
#     day = fields.Selection([
#         ('monday', 'Monday'),
#         ('tuesday', 'Tuesday'),
#         ('wednesday', 'Wednesday'),
#         ('thursday', 'Thursday'),
#         ('friday', 'Friday'),
#         ('saturday', 'Saturday'),
#         ('sunday', 'Sunday'),
#     ], string='Day', compute='_compute_day', store=True, readonly=False)
#
#     shift = fields.Selection([
#         ('8_hours', '8 Hours'),
#         ('12_hours', '12 Hours'),
#     ], string='Shift', default='8_hours')
#     operator_name = fields.Many2one('operator.name', string='Operator Name')
#
#     customer_1_id = fields.Many2one('res.partner', string='1st Customer Name')
#     job_order_1_id = fields.Many2one('brand.job.order', string='1st Job Order No.')
#     customer_2_id = fields.Many2one('res.partner', string='2nd Customer Name')
#     job_order_2_id = fields.Many2one('brand.job.order', string='2nd Job Order No.')
#
#     running_line_ids = fields.One2many('production.log.running.line', 'log_sheet_id', string='Running Time')
#     stop_line_ids = fields.One2many('production.log.stop.line', 'log_sheet_id', string='Stop Time')
#     packing_line_ids = fields.One2many('production.log.packing.line', 'log_sheet_id', string='Final Product Packing')
#     byproduct_line_ids = fields.One2many('production.log.byproduct.line', 'log_sheet_id', string='By-Product Summary')
#
#     total_running_time = fields.Float(string='Total Running Time', compute='_compute_total_running_time',
#                                       store=True, readonly=True)
#     total_down_time = fields.Float(string='Total Down Time', compute='_compute_total_down_time',
#                                    store=True, readonly=True)
#
#     prepared_by = fields.Char(string='Prepared By')
#     supervisor = fields.Char(string='Production Supervisor')
#     production_head = fields.Char(string='Production Head')
#     is_reworking = fields.Boolean(string="Reworking", default=False)
#
#     remarks = fields.Html(string='Remarks')
#
#     state = fields.Selection([
#         ('draft', 'Draft'), ('confirmed', 'Confirmed'), ('cancel', 'Cancelled')
#     ], string='Status', default='draft', tracking=True)
#
#     @api.model_create_multi
#     def create(self, vals_list: List[Dict[str, Any]]) -> 'ProductionLogSheet':
#         for vals in vals_list:
#             if vals.get('name', _('New')) == _('New'):
#                 seq_code = 'production.log.sheet.rework' if vals.get('is_reworking') else 'production.log.sheet'
#                 vals['name'] = self.env['ir.sequence'].next_by_code(seq_code) or _('New')
#         records = super().create(vals_list)
#
#         # GUARANTEE LAYER: seed stop lines from the running lines' stop times
#         # on creation (the payment-voucher lesson: onchanges are suggestions;
#         # the server enforces after save).
#         records._seed_stop_lines_from_running()
#         return records
#
#     def write(self, vals: Dict[str, Any]) -> bool:
#         result = super().write(vals)
#
#         # GUARANTEE LAYER: form saves arrive as running_line_ids commands on
#         # this write - seed any unmapped stop times in the same transaction.
#         if 'running_line_ids' in vals:
#             self._seed_stop_lines_from_running()
#         return result
#
#     def _seed_stop_lines_from_running(self) -> None:
#         """Protocol 2.1 (SRP) & 4.1 (DRY): server-side seeding of the Stop
#         Time tab - every Running line stop time with no matching stop line
#         gets one (Stop Time set; Start Time left empty for the restart entry
#         that computes downtime).
#
#         The authoritative twin of the header onchange: runs on create, on
#         parent writes that carry running-line commands, and on direct
#         running-line writes. Idempotent and append-only: duplicate stop
#         times are not re-seeded, existing stop lines keep their typed
#         values, nothing is ever removed."""
#         for log_sheet in self:
#             seeded_stop_times = {
#                 stop_line.stop_time
#                 for stop_line in log_sheet.stop_line_ids
#                 if stop_line.stop_time
#             }
#             running_stop_times = {
#                 line.stop_time
#                 for line in log_sheet.running_line_ids
#                 if line.stop_time
#             }
#             missing_stop_times = running_stop_times - seeded_stop_times
#             if not missing_stop_times:
#                 continue
#
#             self.env['production.log.stop.line'].create([
#                 {
#                     'log_sheet_id': log_sheet.id,
#                     'stop_time': stop_time,
#                 }
#                 for stop_time in sorted(missing_stop_times)
#             ])
#
#     @api.depends('bm1_plant_ids.name')
#     def _compute_bm1_plant(self) -> None:
#         """Machinery: the legacy selection key derived from the first selected
#         plant tag (downstream consumers and reports keep working)."""
#         for rec in self:
#             first_plant_name = rec.bm1_plant_ids[:1].name
#             rec.bm1_plant = PLANT_SELECTION_KEY_MAP.get(first_plant_name or '', False)
#
#     @api.depends('date')
#     def _compute_day(self) -> None:
#         for rec in self:
#             rec.day = WEEKDAY_KEYS[rec.date.weekday()] if rec.date else 'monday'
#
#     @api.depends('running_line_ids.actual_time')
#     def _compute_total_running_time(self) -> None:
#         for rec in self:
#             rec.total_running_time = sum(rec.running_line_ids.mapped('actual_time'))
#
#     @api.depends('stop_line_ids.down_time')
#     def _compute_total_down_time(self) -> None:
#         for rec in self:
#             rec.total_down_time = sum(rec.stop_line_ids.mapped('down_time'))
#
#     def action_confirm(self) -> None:
#         for rec in self:
#             if rec.state != 'draft':
#                 raise UserError(_("Only a Draft Log Sheet can be confirmed. Current state: %s.", rec.state))
#             if not rec.running_line_ids and not rec.packing_line_ids:
#                 raise UserError(_("Please add at least one Running Time or Packing line before confirming."))
#             rec.state = 'confirmed'
#
#     def action_cancel(self) -> None:
#         for rec in self:
#             if rec.state not in ('draft', 'confirmed'):
#                 raise UserError(_("Only a Draft or Confirmed Log Sheet can be cancelled. Current state: %s.", rec.state))
#             rec.state = 'cancel'
#
#     def action_reset_to_draft(self) -> None:
#         for rec in self:
#             if rec.state != 'cancel':
#                 raise UserError(_("Only a Cancelled Log Sheet can be reset to draft. Current state: %s.", rec.state))
#             rec.state = 'draft'
#
#     @api.onchange('show_bm1')
#     def _onchange_show_bm1(self):
#         if self.show_bm1:
#             self.show_bm2 = False
#         else:
#             self.bm1_plant_ids = [(5, 0, 0)]
#
#     @api.onchange('show_bm2')
#     def _onchange_show_bm2(self):
#         if self.show_bm2:
#             self.show_bm1 = False
#         else:
#             self.bm2_plant = False
#
#     # ==========================================================
#     # JOB ORDER <-> CUSTOMER PAIRING
#     # The job order is the input (picked first); the customer is derived.
#     # The customer guards keep manual customer edits consistent.
#     # ==========================================================
#
#     @api.onchange('job_order_1_id')
#     def _onchange_job_order_1_id(self) -> None:
#         """1st Job Order selected: map its Customer automatically."""
#         if self.job_order_1_id:
#             self.customer_1_id = self.job_order_1_id.partner_id.id
#
#     @api.onchange('job_order_2_id')
#     def _onchange_job_order_2_id(self) -> None:
#         """2nd Job Order selected: map its Customer automatically."""
#         if self.job_order_2_id:
#             self.customer_2_id = self.job_order_2_id.partner_id.id
#
#     @api.onchange('customer_1_id')
#     def _onchange_customer_1_id(self):
#         """Customer changed manually: clear a job order that no longer matches
#         (its own onchange re-maps the customer on re-selection)."""
#         if self.job_order_1_id and self.job_order_1_id.partner_id != self.customer_1_id:
#             self.job_order_1_id = False
#
#     @api.onchange('customer_2_id')
#     def _onchange_customer_2_id(self):
#         """Customer changed manually: clear a job order that no longer matches."""
#         if self.job_order_2_id and self.job_order_2_id.partner_id != self.customer_2_id:
#             self.job_order_2_id = False
#
#     @api.onchange('job_order_1_id', 'job_order_2_id')
#     def _onchange_job_order_ids_sync_packing_lines(self) -> None:
#         """Auto-populate ONLY the Final Product Packing lines with Process Rice
#         from the selected Brand Job Orders.
#
#         The Running Time lines are NO LONGER auto-populated: the user adds
#         them manually (the Item column and the product sync were removed)."""
#         process_rice_products = self.env['product.product']
#         for job_order in (self.job_order_1_id, self.job_order_2_id):
#             if not job_order:
#                 continue
#             if job_order.process_rice_ids:
#                 process_rice_products |= job_order.process_rice_ids
#             elif job_order.product_id:
#                 process_rice_products |= job_order.product_id
#
#         existing_packing_map: Dict[int, Dict[str, Any]] = {}
#         for line in self.packing_line_ids:
#             if line.product_id and line.product_id in process_rice_products:
#                 existing_packing_map[line.product_id.id] = {
#                     'product_id': line.product_id.id,
#                     'variety': line.variety,
#                     'no_of_bags': line.no_of_bags,
#                     'packing_size': line.packing_size,
#                     'total_weight': line.total_weight,
#                     'percent': line.percent,
#                 }
#
#         packing_line_vals: List[Tuple[int, int, Dict[str, Any]]] = [COMMAND_CLEAR_ALL]
#         for product in process_rice_products:
#             if product.id in existing_packing_map:
#                 packing_line_vals.append((COMMAND_CREATE_NEW, 0, existing_packing_map[product.id]))
#             else:
#                 packing_line_vals.append((COMMAND_CREATE_NEW, 0, {'product_id': product.id}))
#
#         self.packing_line_ids = packing_line_vals
#
#     # ==========================================================
#     # STOP TIME SEEDING - LIVE LAYER
#     # Header-level onchange: fires in the edit paths where Odoo's client
#     # chains parent onchanges from subfield edits (row-dialog adds, some
#     # builds' inline edits). The guaranteed enforcement is the server-side
#     # _seed_stop_lines_from_running twin (create/write above) - the
#     # payment-voucher pattern.
#     # ==========================================================
#
#     @api.onchange('running_line_ids.stop_time')
#     def _onchange_running_stop_time_seed_stop_lines(self) -> None:
#         """Map the Stop Time to the 'Stop Time' tab live (where supported):
#         every stop time entered on a Running line seeds a matching stop line
#         (Stop Time set, Start Time empty for the restart entry).
#
#         Append-only and idempotent - identical to the server twin."""
#         seeded_stop_times = {
#             stop_line.stop_time
#             for stop_line in self.stop_line_ids
#             if stop_line.stop_time
#         }
#         running_stop_times = {
#             line.stop_time
#             for line in self.running_line_ids
#             if line.stop_time
#         }
#         missing_stop_times = running_stop_times - seeded_stop_times
#         if not missing_stop_times:
#             return
#
#         # Value-preserving rebuild: existing lines keep their typed values,
#         # one new line per unmapped stop time (PLS sync pattern).
#         stop_line_vals = [
#             (COMMAND_CREATE_NEW, 0, {
#                 'stop_time': stop_line.stop_time,
#                 'start_time': stop_line.start_time,
#                 'down_time': stop_line.down_time,
#                 'remarks': stop_line.remarks,
#             })
#             for stop_line in self.stop_line_ids
#         ]
#         stop_line_vals.extend(
#             (COMMAND_CREATE_NEW, 0, {'stop_time': stop_time})
#             for stop_time in sorted(missing_stop_times)
#         )
#         self.stop_line_ids = stop_line_vals
#
#     @api.onchange('issue_material_id')
#     def _onchange_issue_material_id_milling_date(self):
#         if self.issue_material_id:
#             self.milling_date = self.issue_material_id.milling_date
#
#
# class ProductionLogRunningLine(models.Model):
#     _name = 'production.log.running.line'
#     _description = 'Production Log - Running Time Line'
#     _order = 'id asc'
#
#     log_sheet_id = fields.Many2one('production.log.sheet', string='Log Sheet', required=True, ondelete='cascade')
#     product_id = fields.Many2one('product.product', string='Item')
#
#     start_time = fields.Float(string='Start Time')
#     stop_time = fields.Float(string='Stop Time')
#     actual_time = fields.Float(
#         string='Actual Time',
#         compute='_compute_actual_time',
#         store=True,
#         readonly=False,
#         help="Computed from Start/Stop (a stop before the start means the run "
#              "crossed midnight). Manually overridable.",
#     )
#     remarks = fields.Char(string='Remarks')
#
#     @api.depends('start_time', 'stop_time')
#     def _compute_actual_time(self) -> None:
#         for line in self:
#             if line.start_time and line.stop_time:
#                 line.actual_time = _elapsed_hours(line.start_time, line.stop_time)
#             else:
#                 line.actual_time = 0.0
#
#     # GUARANTEE LAYER (direct-line path): a stop time written directly on the
#     # line (API/import - the form save already carries it through the parent
#     # write) seeds the log sheet's stop lines server-side.
#     @api.model_create_multi
#     def create(self, vals_list: List[Dict[str, Any]]) -> 'ProductionLogRunningLine':
#         lines = super().create(vals_list)
#         log_sheets = lines.mapped('log_sheet_id')
#         if log_sheets:
#             log_sheets._seed_stop_lines_from_running()
#         return lines
#
#     def write(self, vals: Dict[str, Any]) -> bool:
#         result = super().write(vals)
#         if 'stop_time' in vals:
#             log_sheets = self.mapped('log_sheet_id')
#             if log_sheets:
#                 log_sheets._seed_stop_lines_from_running()
#         return result
#
#
# class ProductionLogStopLine(models.Model):
#     _name = 'production.log.stop.line'
#     _description = 'Production Log - Stop Time Line'
#     _order = 'id asc'
#
#     log_sheet_id = fields.Many2one('production.log.sheet', string='Log Sheet', required=True, ondelete='cascade')
#
#     stop_time = fields.Float(string='Stop Time')
#     start_time = fields.Float(string='Start Time')
#     down_time = fields.Float(
#         string='Down Time',
#         compute='_compute_down_time',
#         store=True,
#         readonly=False,
#         help="Computed from Stop/Restart times (a restart before the stop means "
#              "the downtime crossed midnight). Manually overridable.",
#     )
#     remarks = fields.Char(string='Remarks')
#
#     @api.depends('stop_time', 'start_time')
#     def _compute_down_time(self) -> None:
#         for line in self:
#             if line.stop_time and line.start_time:
#                 line.down_time = _elapsed_hours(line.stop_time, line.start_time)
#             else:
#                 line.down_time = 0.0
#
#
# class ProductionLogPackingLine(models.Model):
#     _name = 'production.log.packing.line'
#     _description = 'Production Log - Final Product Packing Line'
#     _order = 'id asc'
#
#     log_sheet_id = fields.Many2one('production.log.sheet', string='Log Sheet', required=True, ondelete='cascade')
#     product_id = fields.Many2one('product.product', string='Brand')
#     variety = fields.Char(string='Variety')
#     no_of_bags = fields.Integer(string='No. Bags')
#     packing_size = fields.Float(string='Packing Size')
#
#     # T. Wt = No of Bags * Packing Size (server truth after save).
#     total_weight = fields.Float(
#         string='T. Wt',
#         compute='_compute_total_weight',
#         store=True,
#         readonly=False,
#         help="Auto-calculated as No of Bags x Packing Size, editable for "
#              "manual correction.",
#     )
#     percent = fields.Float(string='%')
#
#     @api.depends('no_of_bags', 'packing_size')
#     def _compute_total_weight(self) -> None:
#         """T. Wt = No of Bags * Packing Size."""
#         for line in self:
#             line.total_weight = (line.no_of_bags or 0) * (line.packing_size or 0.0)
#
#     @api.onchange('no_of_bags', 'packing_size')
#     def _onchange_packing_inputs_update_total_weight(self) -> None:
#         """UI twin: T. Wt updates LIVE while typing in the editable list
#         (stored computes only re-fire after save)."""
#         for line in self:
#             line.total_weight = (line.no_of_bags or 0) * (line.packing_size or 0.0)
#
#
# class ProductionLogByproductLine(models.Model):
#     _name = 'production.log.byproduct.line'
#     _description = 'Production Log - By-Product Summary Line'
#     _order = 'id asc'
#
#     log_sheet_id = fields.Many2one('production.log.sheet', string='Log Sheet', ondelete='cascade')
#     wb_ticket_id = fields.Many2one('weighbridge.ticket', string='Weighbridge Ticket', ondelete='cascade')
#
#     product_id = fields.Many2one('product.product', string='Item')
#     bags = fields.Integer(string='Bags')
#     size = fields.Float(string='Size')
#
#     # Weight = Bags * Size (server truth after save; same shape as packing T. Wt).
#     weight = fields.Float(
#         string='Weight',
#         compute='_compute_weight',
#         store=True,
#         readonly=False,
#         help="Auto-calculated as Bags x Size, editable for manual correction.",
#     )
#     percent = fields.Float(string='%')
#
#     @api.depends('bags', 'size')
#     def _compute_weight(self) -> None:
#         """Weight = Bags x Size."""
#         for line in self:
#             line.weight = (line.bags or 0) * (line.size or 0.0)
#
#     @api.onchange('bags', 'size')
#     def _onchange_byproduct_inputs_update_weight(self) -> None:
#         """UI twin: Weight updates LIVE while typing in the editable list."""
#         for line in self:
#             line.weight = (line.bags or 0) * (line.size or 0.0)
#
#     @api.constrains('log_sheet_id', 'wb_ticket_id')
#     def _check_byproduct_line_parent(self) -> None:
#         for line in self:
#             if not line.log_sheet_id and not line.wb_ticket_id:
#                 raise ValidationError(_(
#                     "A Bi-Product line must belong to a Log Sheet or a Weighbridge Ticket."))
#
#
# class OperatorName(models.Model):
#     _name = 'operator.name'
#     _description = 'Operator Name'
#     _order = 'name'
#
#     name = fields.Char(string='Operator Name', required=True)


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

# Machinery mapping: master.plant record name -> legacy selection key
PLANT_SELECTION_KEY_MAP: Dict[str, str] = {
    'Plant A': 'plant_a',
    'Plant B': 'plant_b',
    'Plant C': 'plant_c',
}


def _elapsed_hours(start_time: float, stop_time: float) -> float:
    """Duration between two time-of-day values (float hours).
    A negative difference means the period crossed midnight (night shift)."""
    difference = stop_time - start_time
    if difference < 0:
        difference += HOURS_PER_DAY
    return difference


class MasterPlant(models.Model):
    _name = 'master.plant'
    _description = 'Master Plant'
    _order = 'name asc'

    name = fields.Char(string='Plant Name', required=True)
    active = fields.Boolean(string='Active', default=True,
                            help="Archived plants disappear from selections but keep their history.")


class ProductionLogSheet(models.Model):
    _name = 'production.log.sheet'
    _description = 'Production Log Sheet'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'smart.button.mixin']
    _order = 'id desc'

    name = fields.Char(string='Log No.', index=True, readonly=True, copy=False, default=lambda self: _('New'))

    issue_material_id = fields.Many2one('issue.material', string='Issue Material Ref', ondelete='restrict')
    milling_date = fields.Date(string='Milling Date')

    show_bm1 = fields.Boolean(string="BM 1", default=True)
    show_bm2 = fields.Boolean(string="BM 2", default=False)

    bm1_plant_ids = fields.Many2many(
        'master.plant',
        'pls_bm1_plant_rel',
        'log_sheet_id',
        'plant_id',
        string='BM-1 Plants',
        help="The BM-1 plants this shift ran on. Select multiple when the shift covered several plants.",
    )

    bm1_plant = fields.Selection([
        ('plant_a', 'Plant A'),
        ('plant_b', 'Plant B'),
        ('plant_c', 'Plant C')
    ], string='BM-1 (legacy)', compute='_compute_bm1_plant', store=True)

    bm2_plant = fields.Selection([
        ('plant_a', 'Plant A')
    ], string='BM-2')

    date = fields.Date(string='Date', default=fields.Date.today(), required=True)

    day = fields.Selection([
        ('monday', 'Monday'),
        ('tuesday', 'Tuesday'),
        ('wednesday', 'Wednesday'),
        ('thursday', 'Thursday'),
        ('friday', 'Friday'),
        ('saturday', 'Saturday'),
        ('sunday', 'Sunday'),
    ], string='Day', compute='_compute_day', store=True, readonly=False)

    shift = fields.Selection([
        ('8_hours', '8 Hours'),
        ('12_hours', '12 Hours'),
    ], string='Shift', default='8_hours')
    operator_name = fields.Many2one('operator.name', string='Operator Name')

    customer_1_id = fields.Many2one('res.partner', string='1st Customer Name')
    job_order_1_id = fields.Many2one('brand.job.order', string='1st Job Order No.')
    customer_2_id = fields.Many2one('res.partner', string='2nd Customer Name')
    job_order_2_id = fields.Many2one('brand.job.order', string='2nd Job Order No.')

    running_line_ids = fields.One2many('production.log.running.line', 'log_sheet_id', string='Running Time')
    stop_line_ids = fields.One2many('production.log.stop.line', 'log_sheet_id', string='Stop Time')
    packing_line_ids = fields.One2many('production.log.packing.line', 'log_sheet_id', string='Final Product Packing')
    byproduct_line_ids = fields.One2many('production.log.byproduct.line', 'log_sheet_id', string='By-Product Summary')

    total_running_time = fields.Float(string='Total Running Time', compute='_compute_total_running_time',
                                      store=True, readonly=True)
    total_down_time = fields.Float(string='Total Down Time', compute='_compute_total_down_time',
                                   store=True, readonly=True)

    prepared_by = fields.Char(string='Prepared By')
    supervisor = fields.Char(string='Production Supervisor')
    production_head = fields.Char(string='Production Head')
    is_reworking = fields.Boolean(string="Reworking", default=False)

    remarks = fields.Html(string='Remarks')

    state = fields.Selection([
        ('draft', 'Draft'), ('confirmed', 'Confirmed'), ('cancel', 'Cancelled')
    ], string='Status', default='draft', tracking=True)

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'ProductionLogSheet':
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                seq_code = 'production.log.sheet.rework' if vals.get('is_reworking') else 'production.log.sheet'
                vals['name'] = self.env['ir.sequence'].next_by_code(seq_code) or _('New')
        records = super().create(vals_list)
        records._seed_stop_lines_from_running()
        return records

    def write(self, vals: Dict[str, Any]) -> bool:
        result = super().write(vals)
        if 'running_line_ids' in vals:
            self._seed_stop_lines_from_running()
        return result

    def _seed_stop_lines_from_running(self) -> None:
        """Protocol 2.1 (SRP) & 4.1 (DRY): server-side seeding of the Stop tab."""
        for log_sheet in self:
            runs = log_sheet.running_line_ids.sorted('start_time')
            if not runs:
                continue
            seeded_stop_times = {sl.stop_time for sl in log_sheet.stop_line_ids if sl.stop_time}
            new_stop_vals = []
            for i, run in enumerate(runs):
                if run.stop_time and run.stop_time not in seeded_stop_times:
                    next_start = runs[i + 1].start_time if (i + 1) < len(runs) else 0.0
                    new_stop_vals.append((0, 0, {
                        'log_sheet_id': log_sheet.id,
                        'stop_time': run.stop_time,
                        'start_time': next_start,
                        'remarks': 'Auto-Sync: Machine Stop',
                    }))
            if new_stop_vals:
                log_sheet.write({'stop_line_ids': new_stop_vals})

    @api.depends('bm1_plant_ids.name')
    def _compute_bm1_plant(self) -> None:
        for rec in self:
            first_plant_name = rec.bm1_plant_ids[:1].name
            rec.bm1_plant = PLANT_SELECTION_KEY_MAP.get(first_plant_name or '', False)

    @api.depends('date')
    def _compute_day(self) -> None:
        for rec in self:
            rec.day = WEEKDAY_KEYS[rec.date.weekday()] if rec.date else 'monday'

    @api.depends('running_line_ids.actual_time')
    def _compute_total_running_time(self) -> None:
        for rec in self:
            rec.total_running_time = sum(rec.running_line_ids.mapped('actual_time'))

    @api.depends('stop_line_ids.down_time')
    def _compute_total_down_time(self) -> None:
        for rec in self:
            rec.total_down_time = sum(rec.stop_line_ids.mapped('down_time'))

    def action_confirm(self) -> None:
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Only a Draft Log Sheet can be confirmed."))
            rec.state = 'confirmed'

    def action_cancel(self) -> None:
        for rec in self:
            rec.state = 'cancel'

    def action_reset_to_draft(self) -> None:
        for rec in self:
            rec.state = 'draft'

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

    @api.onchange('job_order_1_id')
    def _onchange_job_order_1_id(self) -> None:
        if self.job_order_1_id: self.customer_1_id = self.job_order_1_id.partner_id.id

    @api.onchange('job_order_2_id')
    def _onchange_job_order_2_id(self) -> None:
        if self.job_order_2_id: self.customer_2_id = self.job_order_2_id.partner_id.id

    @api.onchange('customer_1_id')
    def _onchange_customer_1_id(self):
        if self.job_order_1_id and self.job_order_1_id.partner_id != self.customer_1_id:
            self.job_order_1_id = False

    @api.onchange('customer_2_id')
    def _onchange_customer_2_id(self):
        if self.job_order_2_id and self.job_order_2_id.partner_id != self.customer_2_id:
            self.job_order_2_id = False

    @api.onchange('job_order_1_id', 'job_order_2_id')
    def _onchange_job_order_ids_sync_packing_lines(self) -> None:
        process_rice_products = self.env['product.product']
        for job_order in (self.job_order_1_id, self.job_order_2_id):
            if not job_order: continue
            if job_order.process_rice_ids:
                process_rice_products |= job_order.process_rice_ids
            elif job_order.product_id:
                process_rice_products |= job_order.product_id

        existing_packing_map: Dict[int, Dict[str, Any]] = {}
        for line in self.packing_line_ids:
            if line.product_id and line.product_id in process_rice_products:
                existing_packing_map[line.product_id.id] = {
                    'product_id': line.product_id.id,
                    'brand_manual': line.brand_manual,
                    'variety': line.variety,
                    'no_of_bags': line.no_of_bags,
                    'packing_size': line.packing_size,
                    'total_weight': line.total_weight,
                    'percent': line.percent,
                }

        packing_line_vals: List[Tuple[int, int, Dict[str, Any]]] = [COMMAND_CLEAR_ALL]
        for product in process_rice_products:
            if product.id in existing_packing_map:
                packing_line_vals.append((COMMAND_CREATE_NEW, 0, existing_packing_map[product.id]))
            else:
                packing_line_vals.append((COMMAND_CREATE_NEW, 0, {
                    'product_id': product.id,
                    'variety': product.name,
                }))
        self.packing_line_ids = packing_line_vals

    @api.onchange('running_line_ids')
    def _onchange_running_stop_time_seed_stop_lines(self) -> None:
        runs = self.running_line_ids.sorted('start_time')
        if not runs: return
        existing_stops = {(sl.stop_time, sl.start_time) for sl in self.stop_line_ids}
        new_lines = []
        for i, run in enumerate(runs):
            if run.stop_time:
                next_start = runs[i + 1].start_time if (i + 1) < len(runs) else 0.0
                if (run.stop_time, next_start) not in existing_stops:
                    new_lines.append((0, 0, {
                        'stop_time': run.stop_time,
                        'start_time': next_start,
                        'remarks': 'Auto-Sync',
                    }))
        if new_lines:
            self.stop_line_ids = [(4, s.id) for s in self.stop_line_ids.filtered(lambda x: x.id)] + new_lines

    @api.onchange('issue_material_id')
    def _onchange_issue_material_id_milling_date(self):
        if self.issue_material_id:
            self.milling_date = self.issue_material_id.milling_date


class ProductionLogRunningLine(models.Model):
    _name = 'production.log.running.line'
    _description = 'Production Log - Running Time Line'
    _order = 'id asc'

    log_sheet_id = fields.Many2one('production.log.sheet', string='Log Sheet', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Item')
    start_time = fields.Float(string='Start Time')
    stop_time = fields.Float(string='Stop Time')
    actual_time = fields.Float(string='Actual Time', compute='_compute_actual_time', store=True, readonly=False)
    remarks = fields.Char(string='Remarks')

    @api.depends('start_time', 'stop_time')
    def _compute_actual_time(self) -> None:
        for line in self:
            line.actual_time = _elapsed_hours(line.start_time,
                                              line.stop_time) if line.start_time and line.stop_time else 0.0

    @api.model_create_multi
    def create(self, vals_list: List[Dict[str, Any]]) -> 'ProductionLogRunningLine':
        lines = super().create(vals_list)
        log_sheets = lines.mapped('log_sheet_id')
        if log_sheets: log_sheets._seed_stop_lines_from_running()
        return lines

    def write(self, vals: Dict[str, Any]) -> bool:
        result = super().write(vals)
        if 'stop_time' in vals or 'start_time' in vals:
            self.mapped('log_sheet_id')._seed_stop_lines_from_running()
        return result


class ProductionLogStopLine(models.Model):
    _name = 'production.log.stop.line'
    _description = 'Production Log - Stop Time Line'
    _order = 'id asc'

    log_sheet_id = fields.Many2one('production.log.sheet', string='Log Sheet', required=True, ondelete='cascade')
    stop_time = fields.Float(string='Stop Time')
    start_time = fields.Float(string='Start Time')
    down_time = fields.Float(string='Down Time', compute='_compute_down_time', store=True, readonly=False)
    remarks = fields.Char(string='Remarks')

    @api.depends('stop_time', 'start_time')
    def _compute_down_time(self) -> None:
        for line in self:
            line.down_time = _elapsed_hours(line.stop_time,
                                            line.start_time) if line.stop_time and line.start_time else 0.0


class ProductionLogPackingLine(models.Model):
    _name = 'production.log.packing.line'
    _description = 'Production Log - Final Product Packing Line'
    _order = 'id asc'

    log_sheet_id = fields.Many2one('production.log.sheet', string='Log Sheet', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Brand')
    brand_manual = fields.Char(string='Brand (Manual)')
    variety = fields.Char(string='Variety')
    no_of_bags = fields.Integer(string='No. Bags')
    packing_size = fields.Float(string='Packing Size')

    total_weight = fields.Float(
        string='T. Wt (MT)',
        compute='_compute_total_weight',
        store=True,
        readonly=False,
    )
    percent = fields.Float(string='%')

    @api.depends('no_of_bags', 'packing_size')
    def _compute_total_weight(self) -> None:
        for line in self:
            line.total_weight = ((line.no_of_bags or 0) * (line.packing_size or 0.0)) / 1000.0

    @api.onchange('no_of_bags', 'packing_size')
    def _onchange_packing_inputs_update_total_weight(self) -> None:
        for line in self:
            line.total_weight = ((line.no_of_bags or 0) * (line.packing_size or 0.0)) / 1000.0


class ProductionLogByproductLine(models.Model):
    _name = 'production.log.byproduct.line'
    _description = 'Production Log - By-Product Summary Line'
    _order = 'id asc'

    log_sheet_id = fields.Many2one('production.log.sheet', string='Log Sheet', ondelete='cascade')
    wb_ticket_id = fields.Many2one('weighbridge.ticket', string='Weighbridge Ticket', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Item')
    bags = fields.Integer(string='Bags')
    size = fields.Float(string='Size')

    # CHANGE: Field label updated to MT and precision confirmed
    weight = fields.Float(
        string='Weight (MT)',
        compute='_compute_weight',
        store=True,
        readonly=False
    )
    percent = fields.Float(string='%')

    # CHANGE: Logic updated to convert By-product KG to MT
    @api.depends('bags', 'size')
    def _compute_weight(self) -> None:
        """Weight = (Bags x Size) / 1000 for MT conversion."""
        for line in self:
            line.weight = ((line.bags or 0) * (line.size or 0.0)) / 1000.0

    # CHANGE: Live UI calculation for MT
    @api.onchange('bags', 'size')
    def _onchange_byproduct_inputs_update_weight(self) -> None:
        """Live MT calculation for UI."""
        for line in self:
            line.weight = ((line.bags or 0) * (line.size or 0.0)) / 1000.0

    @api.constrains('log_sheet_id', 'wb_ticket_id')
    def _check_byproduct_line_parent(self) -> None:
        for line in self:
            if not line.log_sheet_id and not line.wb_ticket_id:
                raise ValidationError(_("A Bi-Product line must belong to a Log Sheet or a Weighbridge Ticket."))


class OperatorName(models.Model):
    _name = 'operator.name'
    _description = 'Operator Name'
    _order = 'name'
    name = fields.Char(string='Operator Name', required=True)

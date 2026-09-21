from odoo import api, fields, models


class LoadingContainerPackingListLine(models.Model):
    _name = 'loading.container.packing.list.line'
    _description = 'Loading Container Packing List Line'
    _order = 'sequence, id'

    # =========================================================
    # Parent Packing List
    # =========================================================

    packing_list_id = fields.Many2one(
        'loading.container.packing.list',
        string='Packing List',
        required=True,
        ondelete='cascade',
    )

    # =========================================================
    # Serial Number
    # =========================================================

    sequence = fields.Integer(
        string='Sr No.',
        default=10,
    )

    # =========================================================
    # Container Information
    # =========================================================

    container_no = fields.Char(
        string='Container No.',
        required=True,
        copy=False,
    )

    seal_no = fields.Char(
        string='Seal No.',
        required=True,
        copy=False,
    )

    no_of_bags = fields.Integer(
        string='No. of Bags',
        required=True,
        default=0,
    )

    gross_weight = fields.Float(
        string='Gross Weight (kg)',
        required=True,
    )

    net_weight = fields.Float(
        string='Net Weight (kg)',
        required=True,
    )

    tare_weight = fields.Float(
        string='Tare Weight (kg)',
        compute='_compute_tare_weight',
        store=True,
    )

    vgm = fields.Float(
        string='VGM (kg)',
        required=True,
    )

    # =========================================================
    # Survey / Inspection
    # =========================================================

    survey_agency = fields.Char(
        string='Survey/Inspection Agency',
    )

    survey_report_no = fields.Char(
        string='Survey Report No.',
    )

    loading_date = fields.Date(
        string='Loading Date',
    )

    terminal_port = fields.Char(
        string='Terminal/Port',
    )

    # =========================================================
    # Related Information
    # =========================================================

    booking_id = fields.Many2one(
        'vessel.booking',
        string='Booking No.',
        related='packing_list_id.booking_id',
        store=True,
        readonly=True,
    )

    vessel_name_voyage = fields.Char(
        string='Vessel Name & Voyage',
        related='packing_list_id.vessel_name_voyage',
        store=True,
        readonly=True,
    )

    shipping_line = fields.Char(
        string='Shipping Line',
        related='packing_list_id.shipping_line',
        store=True,
        readonly=True,
    )

    cro_id = fields.Many2one(
        'container.release.order',
        string='CRO No.',
        related='packing_list_id.cro_id',
        store=True,
        readonly=True,
    )

    contract_no = fields.Many2one(
        'rice.sales.contract',
        string='Contract No.',
        related='packing_list_id.contract_no',
        store=True,
        readonly=True,
    )

    # =========================================================
    # Compute Tare Weight
    # =========================================================

    @api.depends(
        'no_of_bags',
        'packing_list_id.bag_tare_weight',
    )
    def _compute_tare_weight(self):

        for line in self:

            line.tare_weight = (
                line.no_of_bags
                * (line.packing_list_id.bag_tare_weight or 0.0)
            )

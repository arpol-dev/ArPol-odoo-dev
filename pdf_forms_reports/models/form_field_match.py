# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools, _


class FormFieldLine(models.Model):
    _name = 'res.form.field.line'
    _description = 'Form field value mapping'

    is_manual = fields.Boolean(string='Manual Entry', default=False)
    name = fields.Char(string='Form Field Name')
    description = fields.Text(string='Description')
    field_type = fields.Selection([
        ('text', 'Text'),
        ('checkbox', 'Checkbox'),
    ], string='Field Type', required=True)
    report_id = fields.Many2one('ir.actions.report', string='Report', ondelete='cascade')
    evaluation_type = fields.Selection([
        ('value', 'Value'),
        ('reference', 'Reference to a field'),
        ('file', 'File'),
        ('equation', 'Python expression')
    ], 'Evaluation Type', default='value', required=True, change_default=True)
    field_value = fields.Char(string='Value')
    field_reference = fields.Many2one(
        'ir.model.fields',
        string='Field Reference',
        help="Reference to a field in the model. "
    )
    field_bool = fields.Boolean(string='Boolean Value')
    page = fields.Integer(string='Page Number', help="Page number in the PDF form where the field is added. Starting from 1. Negatives are allowed.", default=-1)
    position = fields.Char(
        string='Position',
        help="Position of the field in the PDF form. "
             "Format: x1,y1,x2,y2 (top-left and bottom-right coordinates)."
    )
    field_file = fields.Binary(string='Add document', attachment=True)
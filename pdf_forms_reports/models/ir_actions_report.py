# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError, AccessError, RedirectWarning
import fitz  # PyMuPDF
import io
import base64
import re
from datetime import datetime
from num2words import num2words
import pdb

class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    report_type = fields.Selection(selection_add=[('pdf_form', 'PDF Form')], ondelete={'pdf_form': 'cascade'})
    pdf_form_template = fields.Binary(string='PDF Form Template', attachment=True, required=True)
    form_fields_match = fields.One2many(
        'res.form.field.line',
        'report_id',
        string='Form Fields Mapping',
        help="Mapping of form fields to be filled in the PDF form. "
             "The field name should match the field name in the PDF form."
    )
    signature_image = fields.Binary(string='Signature Image', attachment=True)
    signature_position = fields.Char(
        string='Signature Position', 
        help="Position of the signature in the PDF form."
             "Format: x1,y1,x2,y2 (top-left and bottom-right coordinates)."
    )

    @api.onchange('pdf_form_template')
    def _onchange_pdf_form_template(self):
        # When the pdf form template is updated, create a new record in res.form.field.line
        # for each field in the PDF form

        # Clear existing field mappings
        self.form_fields_match.unlink()

        if self.pdf_form_template:
            pdf_stream = io.BytesIO(base64.b64decode(self.pdf_form_template))
            pdf_document = fitz.open(stream=pdf_stream, filetype="pdf")            

            # Extract fields from the PDF form
            for page in pdf_document:
                for field in page.widgets():
                    if field.field_name:
                        new_match = self.env['res.form.field.line'].create({
                            'name': field.field_name,
                            'field_type': 'text',  # Default to text, can be changed later
                            'page': page.number + 1,  # Page number is 0-indexed in PyMuPDF
                        })
                        self.form_fields_match += new_match

            pdf_document.close()

    def _render_pdf_form(self, res_ids, data=None):
        """
        Render a PDF form by filling in the fields with data from the records.
        """
        # Load the PDF template from the binary field
        pdf_stream = io.BytesIO(base64.b64decode(self.pdf_form_template))
        pdf_document = fitz.open(stream=pdf_stream, filetype="pdf")

        for match in self.form_fields_match:
            # Find the field in the PDF form and set its value
            if not match.is_manual and (match.field_value or match.field_reference or match.field_bool or match.field_file):
                field = pdf_document[match.page - 1].field(match.name)
                if field:
                    if match.evaluation_type == 'value':
                        field.text = match.field_value
                    elif match.evaluation_type == 'reference':
                        if match.field_reference:
                            record = self.env[match.field_reference.model].browse(res_ids)
                            field.text = str(getattr(record, match.field_reference.name, ""))
                    elif match.evaluation_type == 'equation':
                        # Evaluate the python expression
                        try:
                            field.text = str(eval(match.field_value))
                        except Exception as e:
                            raise UserError("Error evaluating equation for field %s: %s", match.name, e)
                    elif match.evaluation_type == 'file' and match.field_file and match.position:
                        x1, y1, x2, y2 = map(float, match.position.split(','))
                        rect = fitz.Rect(x1, y1, x2, y2)
                        file_stream = io.BytesIO(base64.b64decode(match.field_file))
                        pdf_document[match.page - 1].insert_image(rect, stream=file_stream)
                        pdf_document[-1].insert_image(rect, stream=file_stream)
                    else:
                        raise UserError("Unsupported mapping configuration for field %s", match.name)
                field.update()
            # Handle manual entry fields
            elif match.is_manual and match.position and match.page and (match.field_value or match.field_file or match.field_reference):
                if match.evaluation_type == 'value' and match.field_value:
                    x1, y1, x2, y2 = map(float, match.position.split(','))
                    rect = fitz.Rect(x1, y1, x2, y2)
                    pdf_document[match.page - 1].insert_text(rect.topleft, match.field_value)
                elif match.evaluation_type == 'file' and match.field_file:
                    x1, y1, x2, y2 = map(float, match.position.split(','))
                    rect = fitz.Rect(x1, y1, x2, y2)
                    file_stream = io.BytesIO(base64.b64decode(match.field_file))
                    pdf_document[match.page - 1].insert_image(rect, stream=file_stream)
                elif match.evaluation_type == 'reference' and match.field_reference:
                    x1, y1, x2, y2 = map(float, match.position.split(','))
                    rect = fitz.Rect(x1, y1, x2, y2)
                    record = self.env[match.field_reference.model].browse(res_ids)
                    ref = str(getattr(record, match.field_reference.name, ""))
                    pdf_document[match.page - 1].insert_text(rect.topleft, ref)
                elif match.evaluation_type == 'equation' and match.field_value:
                    x1, y1, x2, y2 = map(float, match.position.split(','))
                    rect = fitz.Rect(x1, y1, x2, y2)
                    try:
                        pdf_document[match.page - 1].insert_text(eval(match.field_value))
                    except Exception as e:
                        raise UserError("Error evaluating equation for field %s: %s", match.name, e)
                else:
                    raise UserError("Unsupported mapping configuration for field %s", match.name)
            else:
                raise UserError("Unsupported mapping configuration for field %s", match.name)

        # Save the filled PDF to a temporary file
        output_stream = io.BytesIO()
        pdf_document.save(output_stream)

        # if res_ids:
    #         _logger.info("The PDF report has been generated for model: %s, records %s.", report_sudo.model, str(res_ids))

        pdf_document.close()

        return output_stream.getvalue()

    # def _render(self, report_ref, res_ids, data=None):
    #     pdb.set_trace()
    #     if self.report_type == 'pdf_form':
    #         return self._render_pdf_form(res_ids, data), 'pdf'
    #     return super(IrActionsReport, self)._render(report_ref, res_ids, data)

    
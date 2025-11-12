# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import fitz  # PyMuPDF
import io
import base64
import logging

_logger = logging.getLogger(__name__)


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    # ========================================
    # FIELDS
    # ========================================

    report_type = fields.Selection(
        selection_add=[('pdf_form', 'PDF Form')],
        ondelete={'pdf_form': 'set default'}
    )

    pdf_form_template = fields.Binary(
        string='PDF Form Template',
        attachment=True,
        help="Upload a PDF form with fillable fields. "
             "The module will automatically detect form fields when you upload the file."
    )

    form_fields_match = fields.One2many(
        'res.form.field.line',
        'report_id',
        string='Form Fields Mapping',
        help="Mapping of form fields to be filled in the PDF form."
    )

    signature_image = fields.Binary(
        string='Signature Image',
        attachment=True,
        help="Optional signature image to add to the PDF"
    )

    signature_position = fields.Char(
        string='Signature Position',
        help="Position of the signature in the PDF form. "
             "Format: x1,y1,x2,y2 (top-left and bottom-right coordinates)."
    )

    # ========================================
    # ONCHANGE METHODS
    # ========================================

    @api.onchange('pdf_form_template')
    def _onchange_pdf_form_template(self):
        """
        Auto-detect form fields when PDF template is uploaded.
        Creates a mapping record for each field found in the PDF.
        """
        # Clear existing field mappings
        if self.form_fields_match:
            self.form_fields_match.unlink()

        if not self.pdf_form_template:
            return

        try:
            # Load PDF document
            pdf_stream = io.BytesIO(base64.b64decode(self.pdf_form_template))
            pdf_document = fitz.open(stream=pdf_stream, filetype="pdf")

            # Extract fields from all pages
            field_list = []
            for page in pdf_document:
                for widget in page.widgets():
                    if widget.field_name:
                        # Determine field type
                        field_type = 'checkbox' if widget.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX else 'text'

                        # Create new mapping record
                        field_list.append((0, 0, {
                            'name': widget.field_name,
                            'field_type': field_type,
                            'page': page.number + 1,  # Convert to 1-indexed
                            'evaluation_type': 'value',
                            'is_manual': False,
                        }))

            self.form_fields_match = field_list
            pdf_document.close()

            _logger.info("PDF Form: Detected %d fields in template", len(field_list))

        except Exception as e:
            _logger.error("Failed to parse PDF form template: %s", str(e))
            raise UserError(_("Invalid PDF template: %s") % str(e))

    # ========================================
    # RENDER METHODS
    # ========================================

    def _render_pdf_form(self, report_ref, res_ids=None, data=None):
        """
        Main rendering method for PDF form reports.
        Generates filled PDF forms from template and record data.

        :param report_ref: Reference to the report (ID, xmlid, or report_name)
        :param res_ids: List of record IDs to generate reports for
        :param data: Additional data (wizard data, options, etc.)
        :return: Tuple (pdf_content, 'pdf')
        """
        # 1. Preparation
        if not data:
            data = {}
        if isinstance(res_ids, int):
            res_ids = [res_ids]
        if not res_ids:
            res_ids = [False]  # Handle case with no records

        data.setdefault('report_type', 'pdf')

        # 2. Get report object
        report_sudo = self._get_report(report_ref)

        if not report_sudo.pdf_form_template:
            raise UserError(_("No PDF form template configured for report '%s'") % report_sudo.name)

        _logger.info("Generating PDF form report '%s' for %d record(s)", report_sudo.name, len(res_ids))

        # 3. Generate PDF for each record
        pdf_streams = []
        for res_id in res_ids:
            try:
                stream = self._generate_pdf_form_for_record(report_sudo, res_id, data)
                pdf_streams.append(stream)
            except Exception as e:
                _logger.error("Failed to generate PDF form for record %s: %s", res_id, str(e))
                # Re-raise to stop processing
                raise UserError(_("Failed to generate PDF form for record %s: %s") % (res_id, str(e)))

        # 4. Merge PDFs if multiple records
        if len(pdf_streams) == 1:
            pdf_content = pdf_streams[0].getvalue()
        else:
            # Use Odoo's built-in merge method
            merged_stream = self._merge_pdfs(pdf_streams)
            pdf_content = merged_stream.getvalue()
            merged_stream.close()

        # 5. Cleanup
        for stream in pdf_streams:
            stream.close()

        _logger.info("PDF form report generated successfully (%d bytes)", len(pdf_content))

        return pdf_content, 'pdf'

    def _generate_pdf_form_for_record(self, report, res_id, data):
        """
        Generate a filled PDF form for a single record.

        :param report: ir.actions.report record
        :param res_id: Record ID (or False for reports without records)
        :param data: Additional data dictionary
        :return: BytesIO stream containing the filled PDF
        """
        # 1. Load PDF template
        pdf_stream = io.BytesIO(base64.b64decode(report.pdf_form_template))
        pdf_document = fitz.open(stream=pdf_stream, filetype="pdf")

        # 2. Get record if res_id provided
        record = None
        if res_id:
            try:
                record = self.env[report.model].browse(res_id)
                if not record.exists():
                    raise UserError(_("Record %s not found in model %s") % (res_id, report.model))
            except Exception as e:
                pdf_document.close()
                raise UserError(_("Failed to load record %s: %s") % (res_id, str(e)))

        # 3. Fill all mapped fields
        for match in report.form_fields_match:
            try:
                self._fill_pdf_field(pdf_document, match, record, data)
            except Exception as e:
                # Log warning but continue with other fields
                _logger.warning(
                    "Failed to fill PDF field '%s' for record %s: %s",
                    match.name, res_id, str(e)
                )

        # 4. Add signature if configured
        if report.signature_image and report.signature_position:
            try:
                self._add_signature(pdf_document, report.signature_image, report.signature_position)
            except Exception as e:
                _logger.warning("Failed to add signature: %s", str(e))

        # 5. Save to stream
        output_stream = io.BytesIO()
        pdf_document.save(output_stream)
        pdf_document.close()

        return output_stream

    # ========================================
    # FIELD FILLING METHODS
    # ========================================

    def _fill_pdf_field(self, pdf_document, match, record, data):
        """
        Fill a single PDF field based on mapping configuration.

        :param pdf_document: fitz.Document object
        :param match: res.form.field.line record (field mapping)
        :param record: Odoo record to get data from (or None)
        :param data: Additional data dictionary
        """
        # Compute the value to insert
        value = self._compute_pdf_field_value(match, record, data)

        if value is None or value == '':
            return  # Skip empty values

        if match.is_manual:
            # Manual field: Insert text/image at specified position
            self._insert_manual_content(pdf_document, match, value)
        else:
            # Form field: Fill the form widget
            self._fill_form_widget(pdf_document, match, value)

    def _compute_pdf_field_value(self, match, record, data):
        """
        Compute the value to insert in the PDF field based on evaluation type.

        :param match: res.form.field.line record
        :param record: Odoo record (or None)
        :param data: Additional data dictionary
        :return: Computed value (str, bool, bytes, or None)
        """
        if match.evaluation_type == 'value':
            # Direct value
            if match.field_type == 'checkbox':
                return match.field_bool
            else:
                return match.field_value

        elif match.evaluation_type == 'reference':
            # Field reference from record
            if not match.field_reference or not record:
                return None

            try:
                value = getattr(record, match.field_reference.name, None)
                if value is None:
                    return None

                # Handle different field types
                if hasattr(value, 'name'):  # Many2one
                    return value.name
                elif hasattr(value, '__iter__') and not isinstance(value, str):  # One2many, Many2many
                    return ', '.join([str(v.name if hasattr(v, 'name') else v) for v in value])
                else:
                    return str(value)
            except Exception as e:
                _logger.warning("Failed to evaluate field reference '%s': %s", match.field_reference.name, str(e))
                return None

        elif match.evaluation_type == 'equation':
            # Python expression
            if not match.field_value:
                return None

            try:
                # Evaluation context
                eval_context = {
                    'object': record,
                    'record': record,
                    'env': self.env,
                    'data': data,
                }
                result = eval(match.field_value, eval_context)
                return str(result) if result is not None else None
            except Exception as e:
                _logger.error("Failed to evaluate equation '%s': %s", match.field_value, str(e))
                raise UserError(_("Error evaluating equation for field %s: %s") % (match.name, str(e)))

        elif match.evaluation_type == 'file':
            # Binary file (image)
            return match.field_file

        return None

    def _fill_form_widget(self, pdf_document, match, value):
        """
        Fill a PDF form widget (text field or checkbox).

        :param pdf_document: fitz.Document object
        :param match: res.form.field.line record
        :param value: Value to set (str or bool)
        """
        if match.page < 1 or match.page > len(pdf_document):
            _logger.warning("Invalid page number %d for field '%s'", match.page, match.name)
            return

        page = pdf_document.load_page(match.page - 1)  # Convert to 0-indexed

        # Find the widget by name
        widget = page.first_widget
        while widget:
            if widget.field_name == match.name:
                if match.field_type == 'checkbox':
                    # Set checkbox value
                    widget.field_value = bool(value)
                else:
                    # Set text field value
                    widget.field_value = str(value)

                widget.update()
                return

            widget = widget.next

        _logger.warning("Widget '%s' not found on page %d", match.name, match.page)

    def _insert_manual_content(self, pdf_document, match, value):
        """
        Insert text or image at a manual position in the PDF.

        :param pdf_document: fitz.Document object
        :param match: res.form.field.line record
        :param value: Value to insert (str or bytes for image)
        """
        if not match.position:
            _logger.warning("No position specified for manual field '%s'", match.name)
            return

        if match.page < 1 or match.page > len(pdf_document):
            _logger.warning("Invalid page number %d for manual field '%s'", match.page, match.name)
            return

        try:
            # Parse position coordinates
            coords = [float(x.strip()) for x in match.position.split(',')]
            if len(coords) != 4:
                raise ValueError("Position must have 4 coordinates (x1,y1,x2,y2)")

            x1, y1, x2, y2 = coords
            rect = fitz.Rect(x1, y1, x2, y2)

            page = pdf_document.load_page(match.page - 1)

            if match.evaluation_type == 'file' and isinstance(value, bytes):
                # Insert image
                image_stream = io.BytesIO(base64.b64decode(value))
                page.insert_image(rect, stream=image_stream)
            else:
                # Insert text
                page.insert_text(rect.tl, str(value))

        except Exception as e:
            _logger.error("Failed to insert manual content for field '%s': %s", match.name, str(e))
            raise UserError(_("Failed to insert content at position %s: %s") % (match.position, str(e)))

    def _add_signature(self, pdf_document, signature_image, position):
        """
        Add a signature image to the PDF at the specified position.

        :param pdf_document: fitz.Document object
        :param signature_image: Binary signature image data
        :param position: Position string "x1,y1,x2,y2"
        """
        try:
            # Parse position
            coords = [float(x.strip()) for x in position.split(',')]
            if len(coords) != 4:
                raise ValueError("Position must have 4 coordinates")

            x1, y1, x2, y2 = coords
            rect = fitz.Rect(x1, y1, x2, y2)

            # Insert on last page
            last_page = pdf_document.load_page(-1)
            image_stream = io.BytesIO(base64.b64decode(signature_image))
            last_page.insert_image(rect, stream=image_stream)

        except Exception as e:
            raise UserError(_("Failed to add signature: %s") % str(e))

    # ========================================
    # CONSTRAINTS
    # ========================================

    @api.constrains('pdf_form_template', 'report_type')
    def _check_pdf_form_template(self):
        """Validate that PDF form template is a valid PDF file."""
        for report in self:
            if report.report_type == 'pdf_form':
                if not report.pdf_form_template:
                    raise UserError(_("PDF form template is required for report type 'PDF Form'"))

                try:
                    pdf_stream = io.BytesIO(base64.b64decode(report.pdf_form_template))
                    doc = fitz.open(stream=pdf_stream, filetype="pdf")

                    if len(doc) == 0:
                        raise UserError(_("PDF template is empty"))

                    doc.close()
                except Exception as e:
                    raise UserError(_("Invalid PDF template: %s") % str(e))

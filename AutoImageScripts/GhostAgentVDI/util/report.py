#!/usr/bin/python
import logging


__all__ = [
    "generate_html_header",
    "generate_html_footer",
    "generate_table_header",
    "generate_table_footer",
    "generate_row",
    "generate_row_col",
    "generate_hr",
    "generate_table",
]

LOGGER = logging.getLogger(__name__)

# HTML Configuration
_g_charset = "utf-8"

# CSS Configuration
_g_success_css = "Success"
_g_failed_css = "Failed"

_g_css_style = """
<style type="text/css">
    body {
    font: normal 11px auto "Trebuchet MS", Verdana, Arial, Helvetica, sans-serif;
        color: #4f6b72;
        background: #E6EAE9; }
    a {
        color: #c75f3e; }
    #mytable {
        width: 1000px;
        padding: 0;
        margin: 0; }
    caption {
        padding: 0 0 5px 0;
        width: 700px;
    font: italic 11px "Trebuchet MS", Verdana, Arial, Helvetica, sans-serif;
        text-align: right; }
    th {
    font: bold 11px "Trebuchet MS", Verdana, Arial, Helvetica, sans-serif;
        color: #4f6b72;
        border-right: 1px solid #C1DAD7;
        border-bottom: 1px solid #C1DAD7;
        border-top: 1px solid #C1DAD7;
        letter-spacing: 2px;
        text-transform: uppercase;
        text-align: left;
        padding: 6px 6px 6px 12px;
        background: #CAE8EA; }
    th.nobg {
        border-top: 0;
        border-left: 0;
        border-right: 1px solid #C1DAD7;
        background: none; }
    td {
        border-right: 1px solid #C1DAD7;
        border-bottom: 1px solid #C1DAD7;
        background: #fff;
        font-size:11px;
        padding: 6px 6px 6px 12px;
        color: #4f6b72; }
    td.alt {
        background: #F5FAFA;
        color: #797268; }
    td.%s {
        background: #FDE1E2;
        color: #797268; }
    td.%s {
        background: #F5FAFA;
        color: #797268; }
    th.spec {
        border-left: 1px solid #C1DAD7;
        border-top: 0;
        background: #fff;
    font: bold 10px "Trebuchet MS", Verdana, Arial, Helvetica, sans-serif;
    }
    th.specalt {
        border-left: 1px solid #C1DAD7;
        border-top: 0;
        background: #f5fafa;
    font: bold 10px "Trebuchet MS", Verdana, Arial, Helvetica, sans-serif;
        color: #797268; }
    html>body td {
        font-size:11px;}
</style>
""" % (_g_failed_css, _g_success_css)

_g_html_header = """
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=%s" />
<title>Ghost Status Report</title>
""" % (_g_charset)


# Main
def generate_html_header():
    """
    Generate header of report.
    """
    return _g_html_header + _g_css_style + '\n</head>\n<body>'


def generate_html_footer():
    """
    Generate footer of report.
    """
    return '\n</body>'


def generate_table_header(table_name, col_names):
    """
    Generate the table header with col_names automatically.

    :param table_name:
        The table id.
    :param col_names:
        The list of column Name.
    """
    head_content = '\n<table id="%s" cellspacing="0">\n<tr>' % (table_name)
    for index, col_name in enumerate(col_names):
        head_content += ('\n<th scope="col" abbr="header%s">%s</th>'
                         % (index, col_name))
    head_content += '\n</tr>'
    return head_content


def generate_table_footer():
    """
    Generate the table footer.
    """
    return '\n</table>'


def generate_row(col_values, row_css=_g_success_css):
    """
    Generate a row of table with col_values automatically.

    :param col_values:
        The content of each column.
    :param row_css:
        Marked the row with specific CSS.
    """
    row_content = '\n<tr>'
    for col_value in col_values:
        row_content += '\n<td class="%s">%s</td>' % (row_css, col_value)
    row_content += '\n</tr>'
    return row_content


def generate_row_col(col_values, col_csses):
    """
    Generate a row of table with col_values automatically.

    :param col_values:
        The content of each column.
    :param col_csses:
        Marked the column with specific CSS.
    """
    row_content = '\n<tr>'
    for index, col_value in enumerate(col_values):
        row_content += ('\n<td class="%s">%s</td>'
                        % (col_csses[index], col_value))
    row_content += '\n</tr>'
    return row_content


def generate_hr():
    """
    Generate horizontal rule
    Because "FILTER: alpha" is only works on IE, it is not supported.
    """
    return '\n<HR>'


def generate_table(table_name, col_names, row_pairs, add_hr=False):
    """
    Generate a special table.

    :param table_name:
        The table id.
    :param col_names:
        The list of column Name.
    :param row_pairs:
        The list of column values and CSS. Default CSS is "Success".
    :param add_hr:
        Add horizontal after table or not.
    """
    content = generate_table_header(table_name, col_names)
    for row_pair in row_pairs:
        if len(row_pair) == 2 and isinstance(row_pair[0], list):
            css = _g_success_css if row_pair[1] else _g_failed_css
            content += generate_row(row_pair[0], css)
        else:
            content += generate_row(row_pair[0], _g_success_css)
    content += generate_table_footer()
    if add_hr:
        content += generate_hr()
    return content





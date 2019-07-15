import base64
from collections import defaultdict
from decorator import decorator
from operator import attrgetter
import importlib
import io
import logging
import os
import shutil
import tempfile
import zipfile

import requests

from odoo.tools import pycompat

from docutils import nodes
from docutils.core import publish_string
from docutils.transforms import Transform, writer_aux
from docutils.writers.html4css1 import Writer
import lxml.html
import psycopg2

import odoo
from odoo import api, fields, models, modules, tools, _
from odoo.exceptions import AccessDenied, UserError
from odoo.tools.parse_version import parse_version
from odoo.tools.misc import topological_sort
from odoo.http import request

_logger = logging.getLogger(__name__)

class Module(models.Model):
    _inherit = "ir.module.module"

    @api.multi
    def _button_immediate_function(self, function):
        try:
            # This is done because the installation/uninstallation/upgrade can modify a currently
            # running cron job and prevent it from finishing, and since the ir_cron table is locked
            # during execution, the lock won't be released until timeout.
            self._cr.execute("SELECT * FROM ir_cron FOR UPDATE NOWAIT")
        except psycopg2.OperationalError:
            raise UserError(_("The server is busy right now, module operations are not possible at"
                              " this time, please try again later."))
        function(self)

        self._cr.commit()
        api.Environment.reset()
        modules.registry.Registry.new(self._cr.dbname, update_module=True)

        self._cr.commit()
        env = api.Environment(self._cr, self._uid, self._context)
        # pylint: disable=next-method-called
        config = env['ir.module.module'].next() or {}
        _logger.debug(env['ir.module.module'])
        _logger.debug(config)
        if config.get('type') not in ('ir.actions.act_window_close',):
            config['url'] = '/web?debug=1#id=%s&view_type=form&model=ir.module.module' % (self.id)
            _logger.debug(config)
            return config

        # reload the client; open the first available root menu
        menu = env['ir.ui.menu'].search([('parent_id', '=', False)])[:1]
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
            'params': {'menu_id': menu.id},
        }





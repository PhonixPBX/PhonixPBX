"""Import and export of legacy AskoziaPBX (2011, PHP) ``config.xml`` files.

* :mod:`.parse` - XML (defusedxml) to the intermediate :class:`~.parse.Node` model
* :mod:`.upgrade` - older config versions to 2.1 (``convert_config()`` port)
* :mod:`.mapping` - legacy fields to PhonixPBX service inputs and back
* :mod:`.importer` - ``import_bytes()`` / ``import_file()`` (dry run, replace, merge)
* :mod:`.exporter` - ``export()`` to config.xml 2.1
* :mod:`.report` - :class:`~.report.ImportReport` and :class:`~.report.ExportReport`
"""

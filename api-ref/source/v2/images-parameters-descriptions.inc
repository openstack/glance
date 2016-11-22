.. |p-start| raw:: html

    <p>

.. |p-end| raw:: html

    </p>

.. |disk_format_description| replace::
    |p-start|\ The format of the disk.\ |p-end|
    |p-start|\ Responses may vary based on the configuration available in a
    particular OpenStack cloud. See the :ref:`Image Schema <image-schema>`
    response from the cloud itself for the valid values available.\ |p-end|
    |p-start|\ Example formats are: ``ami``, ``ari``, ``aki``, ``vhd``,
    ``vhdx``, ``vmdk``, ``raw``, ``qcow2``, ``vdi``, or ``iso``.\ |p-end|
    |p-start|\ The value might be ``null`` (JSON null data type).\ |p-end|
    **Newton changes**: The ``vhdx`` disk format is a supported value.

from jhub.helpers import import_from_module


def recursive_format(input, value):
    if isinstance(input, list):
        for item_index, item_value in enumerate(input):
            if isinstance(item_value, str):
                try:
                    input[item_index] = item_value.format(**value)
                except KeyError:
                    continue
            recursive_format(item_value, value)
    if isinstance(input, dict):
        for input_key, input_value in input.items():
            if isinstance(input_value, str):
                try:
                    input[input_key] = input_value.format(**value)
                except KeyError:
                    continue
            recursive_format(input_value, value)
    if hasattr(input, "__dict__"):
        recursive_format(input.__dict__, value)


def discover_datatype_klass(datatype, configuration):
    # Discover the helper datatype for the particular
    # supported data type helper
    datatype_klass = import_from_module(
        "jhub.{}".format(datatype),
        datatype,
        "discover_{}_datatype_klass".format(datatype),
    )
    return datatype_klass(configuration)

"""Convert ASN.1 specifications to Python data structures.

"""

import logging
import re
import sys

from pyparsing import Literal
from pyparsing import Keyword
from pyparsing import Word
from pyparsing import ZeroOrMore
from pyparsing import Regex
from pyparsing import printables
from pyparsing import delimitedList
from pyparsing import Group
from pyparsing import Optional
from pyparsing import Forward
from pyparsing import StringEnd
from pyparsing import OneOrMore
from pyparsing import nums
from pyparsing import Suppress
from pyparsing import ParseException
from pyparsing import ParseSyntaxException
from pyparsing import NotAny
from pyparsing import NoMatch
from pyparsing import QuotedString
from pyparsing import Combine
from pyparsing import ParseResults
from pyparsing import lineno

import textparser as tp
from textparser import Sequence
from textparser import choice
from textparser import DelimitedList

from .errors import Error


LOGGER = logging.getLogger(__name__)

EXTENSION_MARKER = None


class Asn1Parser(tp.Parser):

    def keywords(self):
        return set([
            'ABSENT',
            'ENCODED',
            'INTEGER',
            'RELATIVE-OID',
            'ABSTRACT-SYNTAX',
            'END',
            'INTERSECTION',
            'SEQUENCE',
            'ALL',
            'ENUMERATED',
            'ISO646String',
            'SET',
            'APPLICATION',
            'EXCEPT',
            'MAX',
            'SIZE',
            'AUTOMATIC',
            'EXPLICIT',
            'MIN',
            'STRING',
            'BEGIN',
            'EXPORTS',
            'MINUS-INFINITY',
            'SYNTAX',
            'BIT',
            'EXTENSIBILITY',
            'NULL',
            'T61String',
            'BMPString',
            'EXTERNAL',
            'NumericString',
            'TAGS',
            'BOOLEAN',
            'FALSE',
            'OBJECT',
            'TeletexString',
            'BY',
            'FROM',
            'ObjectDescriptor',
            'TRUE',
            'CHARACTER',
            'GeneralizedTime',
            'OCTET',
            'TYPE-IDENTIFIER',
            'CHOICE',
            'GeneralString',
            'OF',
            'UNION',
            'CLASS',
            'GraphicString',
            'OPTIONAL',
            'UNIQUE',
            'COMPONENT',
            'IA5String',
            'PATTERN',
            'UNIVERSAL',
            'COMPONENTS',
            'IDENTIFIER',
            'PDV',
            'UniversalString',
            'CONSTRAINED',
            'IMPLICIT',
            'PLUS-INFINITY',
            'UTCTime',
            'CONTAINING',
            'IMPLIED',
            'PRESENT',
            'UTF8String',
            'DEFAULT',
            'IMPORTS',
            'PrintableString',
            'VideotexString',
            'DEFINITIONS',
            'INCLUDES',
            'PRIVATE',
            'VisibleString',
            'EMBEDDED',
            'INSTANCE',
            'REAL',
            'WITH',
            'ANY',
            'DEFINED'
        ])

    def token_specs(self):
        return [
            ('SKIP',           r'[ \r\n\t]+|--([\s\S]*?(--|\n))'),
            ('NUMBER',         r'-?\d+'),
            ('LVBRACK', '[[',  r'\[\['),
            ('RVBRACK', ']]',  r'\]\]'),
            ('LBRACE',  '{',   r'{'),
            ('RBRACE',  '}',   r'}'),
            ('LT',      '<',   r'<'),
            ('GT',      '>',   r'>'),
            ('COMMA',   ',',   r','),
            ('DOTX3',   '...', r'\.\.\.'),
            ('DOTX2',   '..',  r'\.\.'),
            ('DOT',     '.',   r'\.'),
            ('LPAREN',  '(',   r'\('),
            ('RPAREN',  ')',   r'\)'),
            ('LBRACK',  '[',   r'\['),
            ('RBRACK',  ']',   r'\]'),
            ('MINUS',   '-',   r'-'),
            ('ASSIGN',  '::=', r'::='),
            ('COLON',   ':',   r':'),
            ('EQ',      '=',   r'='),
            ('CSTRING',        r'"[^"]*"'),
            ('QMARK',   '"',   r'"'),
            ('BSTRING',        r"'[01\s]*'B"),
            ('HSTRING',        r"'[0-9A-F\s]*'H"),
            ('APSTR',   "'",   r"'"),
            ('SCOLON',  ';',   r';'),
            ('AT',      '@',   r'@'),
            ('PIPE',    '|',   r'\|'),
            ('EMARK',   '!',   r'!'),
            ('HAT',     '^',   r'\^'),
            ('AMPND',   '&',   r'&'),
            ('TREF',           r'[A-Z][a-zA-Z0-9-]*'),
            ('IDENT',          r'[a-z][a-zA-Z0-9-]*'),
            ('MISMATCH',       r'.')
        ]

    def grammar(self):
        value = tp.Forward()
        type_ = tp.Forward()
        object_ = tp.Forward()
        object_set = tp.Forward()
        primitive_field_name = tp.Forward()
        constraint = tp.Forward()
        element_set_spec = tp.Forward()
        token_or_group_spec = tp.Forward()
        value_set = tp.Forward()
        named_type = tp.Forward()
        root_element_set_spec = tp.Forward()
        defined_object_set = tp.Forward()
        syntax_list = tp.Forward()
        object_from_object = tp.Forward()
        object_set_from_objects = tp.Forward()
        defined_value = tp.Forward()
        component_type_lists = tp.Forward()
        extension_and_exception = tp.Forward()
        optional_extension_marker = tp.Forward()
        additional_element_set_spec = tp.Forward()
        reference = tp.Forward()
        defined_object_class = tp.Forward()
        defined_type = tp.Forward()
        external_type_reference = tp.Forward()
        external_value_reference = tp.Forward()
        simple_defined_type = tp.Forward()
        defined_object = tp.Forward()
        referenced_value = tp.Forward()
        builtin_value = tp.Forward()
        named_value = tp.Forward()
        signed_number = tp.Forward()
        name_and_number_form = tp.Forward()
        number_form = tp.Forward()
        definitive_number_form = tp.Forward()
        version_number = tp.Forward()
        named_number = tp.Forward()
        intersections = tp.Forward()
        unions = tp.Forward()

        # ToDo!
        value_set <<= tp.NoMatch()

        # X680: 11. ASN.1 lexical items
        identifier = 'IDENT'
        value_reference = identifier
        type_reference = 'TREF'
        module_reference = type_reference
        real_number = Sequence('NUMBER', '.', tp.Optional('NUMBER'))
        number = 'NUMBER'

        value_field_reference = Sequence('&',  value_reference)
        type_field_reference = Sequence('&', type_reference)
        word = type_reference

        # X.683: 8. Parameterized assignments
        dummy_reference = reference
        dummy_governor = dummy_reference
        governor = choice(type_, defined_object_class)
        param_governor = choice(governor, dummy_governor)
        parameter = Sequence(tp.Optional(Sequence(param_governor, ':')),
                             dummy_reference)
        parameter_list = tp.Optional(Sequence('{',
                                              DelimitedList(parameter),
                                              '}'))

        # X.683: 9. Referencing parameterized definitions
        actual_parameter = choice(type_,
                                  value,
                                  value_set,
                                  defined_object_class,
                                  object_,
                                  object_set)
        actual_parameter_list = Sequence('{',
                                         DelimitedList(actual_parameter),
                                         '}')
        parameterized_object = Sequence(defined_object,
                                        actual_parameter_list)
        parameterized_object_set = Sequence(defined_object_set,
                                            actual_parameter_list)
        parameterized_object_class = Sequence(defined_object_class,
                                              actual_parameter_list)
        parameterized_value_set_type = Sequence(simple_defined_type,
                                                actual_parameter_list)
        simple_defined_value = choice(external_value_reference,
                                      value_reference)
        parameterized_value = Sequence(simple_defined_value,
                                       actual_parameter_list)
        simple_defined_type <<= choice(external_type_reference,
                                       type_reference)
        parameterized_type = Sequence(simple_defined_type,
                                      actual_parameter_list)
        parameterized_reference = Sequence(reference,
                                           tp.Optional(Sequence('{', '}')))

        # X.682: 11. Contents constraints
        contents_constraint = choice(
            Sequence('CONTAINING',
                     type_,
                     tp.Optional(Sequence('ENCODED', 'BY', value))),
            Sequence('ENCODED', 'BY', value))

        # X.682: 10. Table constraints, including component relation constraints
        level = tp.OneOrMore('.')
        component_id_list = identifier
        at_notation = Sequence('@',
                               choice(component_id_list,
                                      Sequence(level, component_id_list)))
        component_relation_constraint = Sequence('{',
                                                 defined_object_set,
                                                 '}',
                                                 '{',
                                                 DelimitedList(at_notation),
                                                 '}')
        simple_table_constraint = object_set
        table_constraint = choice(component_relation_constraint,
                                  simple_table_constraint)

        # X.682: 9. User-defined constants
        user_defined_constraint_parameter = choice(
            Sequence(governor,
                     ':',
                     choice(value,
                            value_set,
                            object_,
                            object_set)),
            type_,
            defined_object_class)
        user_defined_constraint = Sequence(
            'CONSTRAINED', 'BY',
            '{',
            tp.Optional(DelimitedList(user_defined_constraint_parameter)),
            '}')

        # X.682: 8. General constraint specification
        general_constraint = choice(user_defined_constraint,
                                    table_constraint,
                                    contents_constraint)

        # X.681: 7. ASN.1 lexical items
        object_set_reference = type_reference
        value_set_field_reference = tp.NoMatch()
        object_field_reference = tp.NoMatch()
        object_set_field_reference = tp.NoMatch()
        object_class_reference = type_reference
        object_reference = value_reference

        # X.681: 8. Referencing definitions
        external_object_set_reference = tp.NoMatch()
        defined_object_set <<= choice(external_object_set_reference,
                                      object_set_reference)
        defined_object <<= tp.NoMatch()
        defined_object_class <<= object_class_reference

        # X.681: 9. Information object class definition and assignment
        field_name = primitive_field_name
        primitive_field_name <<= choice(type_field_reference,
                                        value_field_reference,
                                        value_set_field_reference,
                                        object_field_reference,
                                        object_set_field_reference)
        object_set_field_spec = tp.NoMatch()
        object_field_spec = tp.NoMatch()
        variable_type_value_set_field_spec = tp.NoMatch()
        fixed_type_value_set_field_spec = tp.NoMatch()
        variable_type_value_field_spec = tp.NoMatch()
        fixed_type_value_field_spec = Sequence(
            value_field_reference,
            type_,
            tp.Optional('UNIQUE'),
            tp.Optional(choice('OPTIONAL',
                               Sequence('DEFAULT', value))))
        type_field_spec = Sequence(
            type_field_reference,
            tp.Optional(choice('OPTIONAL',
                               Sequence('DEFAULT', type_))))
        field_spec = choice(type_field_spec,
                            fixed_type_value_field_spec,
                            variable_type_value_field_spec,
                            fixed_type_value_set_field_spec,
                            variable_type_value_set_field_spec,
                            object_field_spec,
                            object_set_field_spec)
        with_syntax_spec = Sequence('WITH', 'SYNTAX', syntax_list)
        object_class_defn = Sequence('CLASS',
                                     '{',
                                     DelimitedList(field_spec),
                                     '}',
                                     tp.Optional(with_syntax_spec))
        object_class = choice(object_class_defn,
                              # defined_object_class,
                              parameterized_object_class)
        parameterized_object_class_assignment = Sequence(
            object_class_reference,
            parameter_list,
            '::=',
            object_class)

        # X.681: 10. Syntax list
        literal = choice(word, ',')
        required_token = choice(literal, primitive_field_name)
        optional_group = Sequence('[',
                                  tp.OneOrMore(token_or_group_spec),
                                  ']')
        token_or_group_spec <<= choice(required_token, optional_group)
        syntax_list <<= Sequence('{',
                                 tp.OneOrMore(token_or_group_spec),
                                 '}')

        # X.681: 11. Information object definition and assignment
        setting = choice(type_, value, value_set, object_, object_set, 'CSTRING')
        field_setting = Sequence(primitive_field_name, setting)
        default_syntax = Sequence('{',
                                  DelimitedList(field_setting),
                                  '}')
        defined_syntax = tp.NoMatch()
        object_defn = choice(default_syntax, defined_syntax)
        object_ <<= choice(defined_object,
                           object_defn,
                           object_from_object,
                           parameterized_object)
        parameterized_object_assignment = Sequence(object_reference,
                                                   parameter_list,
                                                   defined_object_class,
                                                   '::=',
                                                   object_)

        # X.681: 12. Information object set definition and assignment
        object_set_elements = choice(object_,
                                     defined_object_set,
                                     object_set_from_objects,
                                     parameterized_object_set)
        object_set_spec = choice(
            Sequence(
                root_element_set_spec,
                tp.Optional(
                    Sequence(',', '...',
                             tp.Optional(
                                 Sequence(',',
                                          additional_element_set_spec))))),
            Sequence('...',
                     tp.Optional(Sequence(',',
                                          additional_element_set_spec))))
        object_set <<= Sequence('{', object_set_spec, '}')
        parameterized_object_set_assignment = Sequence(
            object_set_reference,
            parameter_list,
            defined_object_class,
            '::=',
            object_set)

        # X.681: 13. Associated tables

        # X.681: 14. Notation for the object class field type
        fixed_type_field_val = choice(builtin_value, referenced_value)
        open_type_field_val = Sequence(type_, ':', value)
        object_class_field_value = choice(open_type_field_val,
                                          fixed_type_field_val)
        object_class_field_type = Sequence(defined_object_class,
                                           '.',
                                           field_name)

        # X.681: 15. Information from objects
        object_set_from_objects <<= tp.NoMatch()
        object_from_object <<= tp.NoMatch()

        # X.680: 49. The exception identifier
        exception_identification = choice(signed_number,
                                          defined_value,
                                          Sequence(type_, ":", value))
        exception_spec = tp.Optional(Sequence('!', exception_identification))

        # X.680: 47. Subtype elements
        pattern_constraint = tp.Tag('PatternConstraint',
                                    Sequence('PATTERN', value))
        presence_constraint = tp.Optional(choice('PRESENT', 'ABSENT', 'OPTIONAL'))
        value_constraint = tp.Optional(constraint)
        component_constraint = Sequence(value_constraint, presence_constraint)
        named_constraint = Sequence(identifier, component_constraint)
        type_constraints = DelimitedList(named_constraint)
        partial_specification = Sequence('{', '...', ',', type_constraints, '}')
        full_specification = Sequence('{', type_constraints, '}')
        multiple_type_constraints = choice(full_specification,
                                           partial_specification)
        single_type_constraint = constraint
        inner_type_constraints = tp.Tag(
            'InnerTypeConstraint',
            choice(Sequence('WITH', 'COMPONENT', single_type_constraint),
                   Sequence('WITH', 'COMPONENTS', multiple_type_constraints)))
        permitted_alphabet = tp.Tag('PermittedAlphabet',
                                    Sequence('FROM', constraint))
        type_constraint = tp.Tag('TypeConstraint', type_)
        size_constraint = tp.Tag('SizeConstraint', Sequence('SIZE', constraint))
        lower_end_value = choice(value, 'MIN')
        upper_end_value = choice(value, 'MAX')
        lower_endpoint = Sequence(lower_end_value, tp.Optional('<'))
        upper_endpoint = Sequence(tp.Optional('<'), upper_end_value)
        value_range = tp.Tag('ValueRange',
                             Sequence(lower_endpoint, '..', upper_endpoint))
        includes = tp.Optional('INCLUDES')
        contained_subtype = tp.Tag('ContainedSubtype', Sequence(includes, type_))
        single_value = tp.Tag('SingleValue', value)
        subtype_elements = choice(size_constraint,
                                  permitted_alphabet,
                                  value_range,
                                  inner_type_constraints,
                                  single_value,
                                  pattern_constraint,
                                  contained_subtype,
                                  type_constraint)

        # X.680: 46. Element set specification
        elements = choice(subtype_elements,
                          object_set_elements,
                          Sequence('(', element_set_spec, ')'))
        intersection_mark = choice('^', 'INTERSECTION')
        union_mark = choice('|', 'UNION')
        exclusions = Sequence('EXCEPT', elements)
        intersection_elements = Sequence(elements, tp.Optional(exclusions))
        intersections <<= choice(intersection_elements,
                                 Sequence(intersections,
                                          intersection_mark,
                                          intersection_elements))
        unions <<= DelimitedList(elements, delim=choice(union_mark,
                                                        intersection_mark))
        element_set_spec <<= choice(unions, Sequence('ALL', exclusions))
        additional_element_set_spec <<= element_set_spec
        root_element_set_spec <<= element_set_spec
        element_set_specs = Sequence(
            root_element_set_spec,
            tp.Optional(Sequence(',', '...',
                                 tp.Optional(
                                     Sequence(',', additional_element_set_spec)))))

        # X.680: 45. Constrained types
        subtype_constraint = element_set_specs
        constraint_spec = choice(subtype_constraint, general_constraint)
        constraint <<= Sequence('(', constraint_spec, exception_spec, ')')
        type_with_constraint = tp.Tag('TypeWithConstraint',
                                      Sequence(choice('SET', 'SEQUENCE'),
                                               choice(constraint, size_constraint),
                                               'OF',
                                               choice(type_, named_type)))

        # X.680: 40. Definition of unrestricted character string types
        unrestricted_character_string_type = Sequence('CHARACTER', 'STRING')
        unrestricted_character_string_value = tp.NoMatch()

        # X.680: 39. Canonical order of characters

        # X.680: 38. Specification of the ASN.1 module "ASN.1-CHARACTER-MODULE"

        # X.680: 37. Definition of restricted character string types
        group = number
        plane = number
        row = number
        cell = number
        quadruple = Sequence('{',
                             group, ',',
                             plane, ',',
                             row, ',',
                             cell,
                             '}')
        table_column = number
        table_row = number
        tuple_ = Sequence('{', table_column, ',', table_row, '}')
        chars_defn = choice('CSTRING', quadruple, tuple_, defined_value)
        charsyms = DelimitedList(chars_defn)
        character_string_list = Sequence('{', charsyms, '}')
        restricted_character_string_value = choice('CSTRING',
                                                   character_string_list,
                                                   quadruple,
                                                   tuple_)
        restricted_character_string_type = choice('BMPString',
                                                  'GeneralString',
                                                  'GraphicString',
                                                  'IA5String',
                                                  'ISO646String',
                                                  'NumericString',
                                                  'PrintableString',
                                                  'TeletexString',
                                                  'UTCTime',
                                                  'GeneralizedTime',
                                                  'T61String',
                                                  'UniversalString',
                                                  'UTF8String',
                                                  'VideotexString',
                                                  'VisibleString')

        # X.680: 36. Notation for character string types
        character_string_value = choice(restricted_character_string_value,
                                        unrestricted_character_string_value)
        character_string_type = tp.Tag('CharacterStringType',
                                       choice(restricted_character_string_type,
                                       unrestricted_character_string_type))

        # X.680: 35. The character string types

        # X.680: 34. Notation for the external type
        # external_value = sequence_value

        # X.680: 33. Notation for embedded-pdv type
        # embedded_pdv_value = sequence_value

        # X.680: 32. Notation for relative object identifier type
        relative_oid_components = choice(number_form,
                                         name_and_number_form,
                                         defined_value)
        relative_oid_component_list = tp.OneOrMore(relative_oid_components)
        relative_oid_value = Sequence('{',
                                      relative_oid_component_list,
                                      '}')

        # X.680: 31. Notation for object identifier type
        name_and_number_form <<= Sequence(identifier,
                                          '(',
                                          number_form,
                                          ')')
        number_form <<= choice(number, defined_value)
        name_form = identifier
        obj_id_components = choice(name_and_number_form,
                                   defined_value,
                                   number_form,
                                   name_form)
        obj_id_components_list = tp.OneOrMore(obj_id_components)
        object_identifier_value = choice(
            Sequence('{', obj_id_components_list, '}'),
            Sequence('{', defined_value, obj_id_components_list, '}'))
        object_identifier_type = tp.Tag('ObjectIdentifierType',
                                        Sequence('OBJECT', 'IDENTIFIER'))

        # X.680: 30. Notation for tagged types
        # tagged_value = NoMatch()

        # X.680: 29. Notation for selection types

        # X.680: 28. Notation for the choice types
        alternative_type_list = DelimitedList(named_type)
        extension_addition_alternatives_group = Sequence('[[',
                                                         version_number,
                                                         alternative_type_list,
                                                         ']]')
        extension_addition_alternative = choice(extension_addition_alternatives_group,
                                                named_type)
        extension_addition_alternatives_list = DelimitedList(extension_addition_alternative)
        extension_addition_alternatives = tp.Optional(
            Sequence(',', extension_addition_alternatives_list))
        root_alternative_type_list = alternative_type_list
        alternative_type_lists = Sequence(
            root_alternative_type_list,
            tp.Optional(Sequence(',',
                                 extension_and_exception,
                                 extension_addition_alternatives,
                                 optional_extension_marker)))
        choice_type = tp.Tag('ChoiceType',
                             Sequence('CHOICE',
                                      '{',
                                      alternative_type_lists,
                                      '}'))
        choice_value = Sequence(identifier, ':', value)

        # X.680: 27. Notation for the set-of types
        set_of_type = Sequence('SET', 'OF', choice(type_, named_type))

        # X.680: 26. Notation for the set types
        # set_value = NoMatch()
        set_type = tp.Tag('SetType',
                          Sequence(
                              'SET',
                              '{',
                              tp.Optional(choice(component_type_lists,
                                                 Sequence(extension_and_exception,
                                                          optional_extension_marker))),
                              '}'))

        # X.680: 25. Notation for the sequence-of types
        sequence_of_value = tp.NoMatch()
        sequence_of_type = tp.Tag('SequenceOfType',
                                  Sequence('SEQUENCE', 'OF',
                                           choice(type_, named_type)))

        # X.680: 24. Notation for the sequence types
        component_value_list = DelimitedList(named_value)
        sequence_value = Sequence('{',
                                  tp.Optional(component_value_list),
                                  '}')
        component_type = choice(
            Sequence(named_type,
                     tp.Optional(choice('OPTIONAL',
                                        Sequence('DEFAULT', value)))),
            Sequence('COMPONENTS', 'OF', type_))
        version_number <<= tp.Optional(Sequence(number, ':'))
        extension_addition_group = Sequence('[[',
                                            version_number,
                                            DelimitedList(component_type),
                                            ']]')
        extension_and_exception <<= Sequence('...', tp.Optional(exception_spec))
        extension_addition = choice(component_type, extension_addition_group)
        extension_addition_list = DelimitedList(extension_addition)
        extension_additions = tp.Optional(Sequence(',', extension_addition_list))
        extension_end_marker = Sequence(',', '...')
        optional_extension_marker <<= tp.Optional(Sequence(',', '...'))
        component_type_list = DelimitedList(component_type)
        root_component_type_list = component_type_list
        component_type_lists <<= choice(
            Sequence(root_component_type_list,
                     tp.Optional(Sequence(',',
                                          extension_and_exception,
                                          extension_additions,
                                          choice(Sequence(extension_end_marker,
                                                          ',',
                                                          root_component_type_list),
                                                 optional_extension_marker)))),
            Sequence(extension_and_exception,
                     extension_additions,
                     choice(Sequence(extension_end_marker,
                                     ',',
                                     root_component_type_list),
                            optional_extension_marker)))
        sequence_type = tp.Tag('SequenceType',
                               Sequence('SEQUENCE',
                                        '{',
                                        tp.Optional(choice(component_type_lists,
                                                           Sequence(extension_and_exception,
                                                                    optional_extension_marker))),
                                        '}'))

        # X.680: 23. Notation for the null type
        null_value = 'NULL'
        null_type = tp.Tag('NullType', 'NULL')

        # X.680: 22. Notation for the octetstring type
        # octet_string_value = choice('BSTRING',
        #                       'HSTRING',
        #                       Sequence('CONTAINING', value))
        octet_string_type = tp.Tag('OctetStringType',
                                   Sequence('OCTET', 'STRING'))

        # X.680: 21. Notation for the bitstring type
        bit_string_value = choice('BSTRING',
                                  'HSTRING',
                                  Sequence('{',
                                           tp.Optional(DelimitedList(identifier)),
                                           '}'))
        named_bit = Sequence('IDENT', '(', choice(number, defined_value), ')')
        bit_string_type = tp.Tag('BitStringType',
                                 Sequence('BIT', 'STRING',
                                          tp.Optional(Sequence('{',
                                                               DelimitedList(named_bit),
                                                               '}'))))

        tag = Sequence('[',
                       tp.Optional(choice('UNIVERSAL', 'APPLICATION', 'PRIVATE')),
                       number,
                       ']')
        tagged_type = tp.Tag('TaggedType',
                             Sequence(tag,
                                      tp.Optional(choice('IMPLICIT', 'EXPLICIT')),
                                      type_))

        # X.680: 20. Notation for the real type
        special_real_value = choice('PLUS-INFINITY', 'MINUS-INFINITY')
        numeric_real_value = choice(real_number, sequence_value)
        real_value = choice(numeric_real_value, special_real_value)
        real_type = tp.Tag('RealType', 'REAL')

        # X.680: 19. Notation for the enumerated type
        enumerated_value = identifier
        enumeration_item = choice(named_number, identifier)
        enumeration = DelimitedList(enumeration_item)
        root_enumeration = enumeration
        additional_enumeration = enumeration
        enumerations = Sequence(
            root_enumeration,
            tp.Optional(Sequence(',', '...', exception_spec,
                                 tp.Optional(
                                     Sequence(',', additional_enumeration)))))
        enumerated_type = tp.Tag('EnumeratedType',
                                 Sequence('ENUMERATED', '{', enumerations, '}'))

        # X.680: 18. Notation for the integer type
        integer_value = choice(signed_number, identifier)
        signed_number <<= number
        named_number <<= Sequence(identifier,
                                  '(',
                                  choice(signed_number, defined_value),
                                  ')')
        integer_type = tp.Tag('IntegerType',
                              Sequence('INTEGER',
                                       tp.Optional(Sequence('{',
                                                            DelimitedList(named_number),
                                                            '}'))))

        # X.680: 17. Notation for the boolean type
        boolean_value = choice('TRUE', 'FALSE')
        boolean_type = tp.Tag('BooleanType', 'BOOLEAN')

        any_defined_by_type = Sequence('ANY', 'DEFINED', 'BY', value_reference)

        # X.680: 16. Definition of types and values
        named_value <<= Sequence(identifier, value)
        referenced_value <<= tp.NoMatch()
        builtin_value <<= choice(bit_string_value,
                                 boolean_value,
                                 character_string_value,
                                 choice_value,
                                 relative_oid_value,
                                 sequence_value,
                                 enumerated_value,
                                 real_value,
                                 integer_value,
                                 null_value,
                                 object_identifier_value,
                                 sequence_of_value)
        value <<= choice(object_class_field_value)
        # ,
        # referenced_value,
        # builtin_value)
        builtin_type = choice(choice_type,
                              integer_type,
                              null_type,
                              bit_string_type,
                              octet_string_type,
                              enumerated_type,
                              'IA5String',
                              boolean_type,
                              real_type,
                              character_string_type,
                              object_class_field_type,
                              sequence_type,
                              set_type,
                              sequence_of_type,
                              set_of_type,
                              object_identifier_type,
                              tagged_type,
                              any_defined_by_type,
                              'ANY',
                              'EXTERNAL')
        named_type <<= Sequence('IDENT', type_)
        referenced_type = tp.Tag('ReferencedType', type_reference)
        type_ <<= choice(Sequence(choice(builtin_type, referenced_type),
                                  tp.ZeroOrMore(constraint)),
                         type_with_constraint)

        # X.680: 15. Assigning types and values
        parameterized_value_assignment = tp.Tag('ParameterizedValueAssignment',
                                                Sequence(value_reference,
                                                         type_,
                                                         '::=',
                                                         value))
        parameterized_type_assignment = tp.Tag('ParameterizedTypeAssignment',
                                               Sequence(type_reference,
                                                        parameter_list,
                                                        '::=',
                                                        type_))

        # X.680: 14. Notation to support references to ASN.1 components

        # X.680: 13. Referencing type and value definitions
        external_value_reference <<= Sequence(module_reference,
                                              '.',
                                              value_reference)
        external_type_reference <<= Sequence(module_reference,
                                             '.',
                                             type_reference)
        defined_type <<= choice(external_type_reference,
                                parameterized_type,
                                parameterized_value_set_type,
                                type_reference)
        defined_value <<= choice(external_value_reference,
                                 parameterized_value,
                                 value_reference)

        # X.680: 12. Module definition
        assignment = choice(parameterized_object_set_assignment,
                            parameterized_object_assignment,
                            parameterized_object_class_assignment,
                            parameterized_type_assignment,
                            parameterized_value_assignment)
        assignment_list = tp.ZeroOrMore(assignment)
        reference <<= choice(type_reference,
                             value_reference,
                             object_class_reference,
                             object_reference,
                             object_set_reference)
        symbol = choice(parameterized_reference,
                        reference)
        symbol_list = DelimitedList(symbol)
        assigned_identifier = tp.Optional(choice(
            object_identifier_value,
            Sequence(defined_value, tp.Not(choice(',', 'FROM')))))
        global_module_reference = Sequence(module_reference, assigned_identifier)
        symbols_from_module = Sequence(symbol_list,
                                       'FROM',
                                       global_module_reference)
        imports = tp.Optional(Sequence('IMPORTS',
                                       tp.ZeroOrMore(symbols_from_module),
                                       ';'))
        symbols_exported = tp.Optional(symbol_list)
        exports = tp.Optional(Sequence('EXPORTS',
                                       choice('ALL', symbols_exported),
                                       ';'))
        module_body = Sequence(exports, imports, assignment_list)
        extension_default = tp.Optional(Sequence('EXTENSIBILITY', 'IMPLIED'))
        tag_default = tp.Optional(
            Sequence(choice('EXPLICIT', 'IMPLICIT', 'AUTOMATIC'), 'TAGS'))
        definitive_name_and_number_form = Sequence(identifier,
                                                   '(',
                                                   definitive_number_form,
                                                   ')')
        definitive_number_form <<= number
        definitive_obj_id_component = choice(definitive_name_and_number_form,
                                             name_form,
                                             definitive_number_form)
        definitive_obj_id_components_list = tp.OneOrMore(definitive_obj_id_component)
        definitive_identifier = tp.Optional(Sequence(
            '{',
            definitive_obj_id_components_list,
            '}'))
        module_identifier = Sequence(module_reference, definitive_identifier)
        module_definition = Sequence(module_identifier,
                                     'DEFINITIONS',
                                     tag_default,
                                     extension_default,
                                     '::=',
                                     'BEGIN',
                                     module_body,
                                     'END')

        return tp.OneOrMore(module_definition)


from pprint import pprint


class Transformer(object):

    def __init__(self):
        self._modules = None
        self._lookup_modules = None

    def transform(self, parse_tree):
        self.setup_lookup_modules(parse_tree)
        self._modules = {}
        
        for module_definition in parse_tree:
            module_name = module_definition[0][0].value
            types = self._lookup_modules[module_name]['types']
            
            for type_name, type_ in types.items():
                self.transform_type(type_name, type_, module_name)

        return self._modules
        
    def setup_lookup_modules(self, parse_tree):
        self._lookup_modules = {}

        for module_definition in parse_tree:
            imports, assignment_list = module_definition[6][1:]
            types = {}
            values = {}

            for tag, assignment in assignment_list:
                if tag == 'ParameterizedTypeAssignment':
                    types[assignment[0].value] = assignment[3]
                elif tag == 'ParameterizedValueAssignment':
                    values[assignment[0].value] = assignment[3]
                else:
                    pass

            module_name = module_definition[0][0].value

            self._lookup_modules[module_name] = {
                'imports': imports,
                'types': types,
                'values': values
            }

    def transform_type(self, type_name, type_, module_name):
        tag = type_[0][0]

        try:
            {
                'BooleanType': self.transform_boolean_type,
                'IntegerType': self.transform_integer_type,
                'RealType': self.transform_real_type,
                'TaggedType': self.transform_tagged_type,
                'ChoiceType': self.transform_choice_type,
                'NullType': self.transform_null_type,
                'BitStringType': self.transform_bit_string_type,
                'OctetStringType': self.transform_octet_string_type,
                'EnumeratedType': self.transform_enumerated_type,
                'CharacterStringType': self.transform_character_string_type,
                'ObjectClassFieldType': self.transform_object_class_field_type,
                'SequenceType': self.transform_sequence_type,
                'SetType': self.transform_set_type,
                'SequenceOfType': self.transform_sequence_of_type,
                'SetOfType': self.transform_set_of_type,
                'ObjectIdentifierType': self.transform_object_identifier_type,
                'TaggedType': self.transform_tagged_type,
                'AnyDefinedByType': self.transform_any_defined_by_type,
                'ReferencedType': self.transform_referenced_type,
                'TypeWithConstraint': self.transform_type_with_constraint
            }[tag](type_name, type_, module_name)
        except KeyError:
            pass

    def transform_parameterized_value_assignment(self, type_name, type_, module_name):
        pass

    def transform_boolean_type(self, type_name, type_, module_name):
        pass

    def transform_integer_type(self, type_name, type_, module_name):
        print()
        pprint(type_name)

        constraints = type_[1]
        
        for constraint in constraints:
            pprint(constraint)

    def transform_real_type(self, type_name, type_, module_name):
        pass

    def transform_tagged_type(self, type_name, type_, module_name):
        pass

    def transform_choice_type(self, type_name, type_, module_name):
        pass

    def transform_null_type(self, type_name, type_, module_name):
        pass

    def transform_bit_string_type(self, type_name, type_, module_name):
        pass

    def transform_octet_string_type(self, type_name, type_, module_name):
        pass

    def transform_enumerated_type(self, type_name, type_, module_name):
        pass

    def transform_character_string_type(self, type_name, type_, module_name):
        pass

    def transform_object_class_field_type(self, type_name, type_, module_name):
        pass

    def transform_sequence_type(self, type_name, type_, module_name):
        pass

    def transform_set_type(self, type_name, type_, module_name):
        pass

    def transform_sequence_of_type(self, type_name, type_, module_name):
        pass

    def transform_set_of_type(self, type_name, type_, module_name):
        pass

    def transform_object_identifier_type(self, type_name, type_, module_name):
        pass

    def transform_any_defined_by_type(self, type_name, type_, module_name):
        pass

    def transform_referenced_type(self, type_name, type_, module_name):
        pass

    def transform_type_with_constraint(self, type_name, type_, module_name):
        pass


class ParseError(Error):
    pass


class InternalParserError(Error):
    pass


class Tokens(object):

    def __init__(self, tag, tokens):
        self.tag = tag
        self.tokens = tokens

    def __getitem__(self, index):
        return self.tokens[index]

    def __len__(self):
        return len(self.tokens)

    def __iter__(self):
        for token in self.tokens:
            yield token

    def __bool__(self):
        return len(self.tokens) > 0

    def __eq__(self, other):
        return other == self.tag

    def __repr__(self):
        return "Tokens(tag='{}', tokens='{}')".format(self.tag,
                                                      self.tokens)


class Tag(Group):

    def __init__(self, tag, expr):
        super(Tag, self).__init__(expr)
        self.tag = tag

    def postParse(self, instring, loc, tokenlist):
        return Tokens(self.tag, tokenlist.asList())


def merge_dicts(dicts):
    return {k: v for d in dicts for k, v in d.items()}


def convert_integer(_s, _l, tokens):
    try:
        return int(tokens[0])
    except (IndexError, ValueError):
        return tokens


def convert_real_number(_s, _l, tokens):
    if '.' not in tokens[0]:
        tokens = int(tokens[0])

    return tokens


def convert_number(token):
    if isinstance(token, list):
        token = token[0]

    try:
        return int(token)
    except (ValueError, TypeError):
        return token


def convert_size(tokens):
    if len(tokens) == 0:
        return None

    tokens = tokens[0]

    if tokens[0] == 'SIZE':
        values = []

        for item_tokens in tokens[1].asList():
            if '..' in item_tokens:
                value = (convert_number(item_tokens[0]),
                         convert_number(item_tokens[2]))
            else:
                value = convert_number(item_tokens[0])

            values.append(value)

        return values
    elif isinstance(tokens[0], dict):
        if 'size' in tokens[0]:
            return tokens[0]['size']


def convert_table(tokens):
    tokens = tokens[0]

    try:
        if isinstance(tokens[1][0][0], list):
            defined_object_set = tokens[1][0][0][0]
        else:
            defined_object_set = tokens[1][0][0]
    except IndexError:
        return None

    try:
        component_ids = tokens[4]
    except IndexError:
        return defined_object_set

    return [defined_object_set, component_ids]


def convert_enum_values(string, location, tokens):
    number = 0
    values = []
    used_numbers = []
    root, extension = tokens
    root = root.asList()
    extension = extension.asList()

    def add_used_numbers(items):
        for item in items:
            if not isinstance(item, list):
                continue

            item_number = int(item[2])

            if item_number in used_numbers:
                raise ParseError(
                    'Duplicated ENUMERATED number {} at line {}.'.format(
                        item_number,
                        lineno(location, string)))

            used_numbers.append(item_number)

    # Root enumeration.
    add_used_numbers(root)

    for token in root:
        if isinstance(token, list):
            values.append((token[0], int(token[2])))
        else:
            while number in used_numbers:
                number += 1

            used_numbers.append(number)
            values.append((token, number))
            number += 1

    # Optional additional enumeration.
    if extension:
        values.append(EXTENSION_MARKER)
        additional = extension[1:]
        add_used_numbers(additional)

        for token in additional:
            if isinstance(token, list):
                number = int(token[2])
                values.append((token[0], number))
            else:
                if number in used_numbers:
                    raise ParseError(
                        'Duplicated ENUMERATED number {} at line {}.'.format(
                            number,
                            lineno(location, string)))

                values.append((token, number))
                used_numbers.append(number)

            number += 1

    return values


def convert_tag(tokens):
    if len(tokens) > 0:
        if len(tokens[0]) == 1:
            tag = {
                'number': int(tokens[0][0])
            }
        else:
            tag = {
                'number': convert_number(tokens[0][1]),
                'class': tokens[0][0]
            }

        if tokens[1]:
            tag['kind'] = tokens[1][0] if tokens[1] else None

        return tag


def convert_value_range(_s, _l, tokens):
    tokens = tokens.asList()
    minimum = tokens[0]

    if isinstance(minimum, list):
        minimum = minimum[0]

    maximum = tokens[1]

    if isinstance(maximum, list):
        maximum = maximum[0]

    return (minimum, maximum)


def convert_inner_type_constraints(_s, _l, tokens):
    tokens = tokens.asList()
    components = []

    for item_tokens in tokens[2]:
        if item_tokens == '...':
            value = EXTENSION_MARKER
        elif len(item_tokens) == 2:
            if isinstance(item_tokens[1], list):
                value = item_tokens[1][0]

                if isinstance(value, list):
                    value = value[0]

                value = (item_tokens[0], value)
            else:
                value = (item_tokens[0], item_tokens[1])
        else:
            value = item_tokens

        components.append(value)

    return {'with-components': components}


def convert_size_constraint(_s, _l, tokens):
    tokens = tokens.asList()[1]
    values = []

    for item_tokens in tokens:
        if item_tokens == '...':
            value = EXTENSION_MARKER
        elif '..' in item_tokens:
            value = (convert_number(item_tokens[0]),
                     convert_number(item_tokens[2]))
        else:
            value = convert_number(item_tokens[0])

        values.append(value)

    return {'size': values}


def convert_permitted_alphabet(_s, _l, tokens):
    tokens = tokens.asList()
    values = []

    for token in tokens[1:]:
        if isinstance(token[0], list):
            for char in token[0][0]:
                values.append((char, char))
        else:
            values.append(token[0])

    return {'from': values}


def convert_constraint(_s, _l, tokens):
    tokens = tokens.asList()
    # print('constraint:', tokens)


def convert_members(tokens):
    members = []

    for member_tokens in tokens:
        if member_tokens in [['...'], '...']:
            members.append(EXTENSION_MARKER)
            continue

        if member_tokens[0] == 'COMPONENTS OF':
            members.append({
                'components-of': member_tokens[1][0]['type']
            })
            continue

        if member_tokens[0] == '[[':
            members.append(convert_members(member_tokens[1]))
            continue

        if len(member_tokens) == 2:
            member_tokens, qualifiers = member_tokens
            qualifiers = qualifiers.asList()
        else:
            qualifiers = []

        member = convert_type(member_tokens[2])
        member['name'] = member_tokens[0]

        if 'OPTIONAL' in qualifiers:
            member['optional'] = True

        if 'DEFAULT' in qualifiers:
            if len(qualifiers[1]) == 0:
                value = []
            else:
                value = convert_value(qualifiers[1], member['type'])

            member['default'] = value

        tag = convert_tag(member_tokens[1])

        if tag:
            member['tag'] = tag

        members.append(member)

    return members


def convert_sequence_type(_s, _l, tokens):
    return {
        'type': 'SEQUENCE',
        'members': convert_members(tokens[2])
    }


def convert_sequence_of_type(_s, _l, tokens):
    converted_type = {
        'type': 'SEQUENCE OF',
        'element': convert_type(tokens[4]),
    }

    if len(tokens[1]) > 0:
        converted_type['size'] = tokens[1][0]['size']

    tag = convert_tag(tokens[3])

    if tag:
        converted_type['element']['tag'] = tag

    return converted_type


def convert_set_type(_s, _l, tokens):
    return {
        'type': 'SET',
        'members': convert_members(tokens[2])
    }


def convert_set_of_type(_s, _l, tokens):
    converted_type = {
        'type': 'SET OF',
        'element': convert_type(tokens[4])
    }

    if len(tokens[1]) > 0:
        converted_type['size'] = tokens[1][0]['size']

    tag = convert_tag(tokens[3])

    if tag:
        converted_type['element']['tag'] = tag

    return converted_type


def convert_choice_type(_s, _l, tokens):
    return {
        'type': 'CHOICE',
        'members': convert_members(tokens[2])
    }


def convert_defined_type(_s, _l, tokens):
    return {
        'type': tokens[0]
    }


def convert_integer_type(_s, _l, _tokens):
    return {'type': 'INTEGER'}


def convert_real_type(_s, _l, _tokens):
    return {'type': 'REAL'}


def convert_enumerated_type(string, location, tokens):
    return {
        'type': 'ENUMERATED',
        'values': convert_enum_values(string, location, tokens[2])
    }


def convert_keyword_type(_s, _l, tokens):
    return {
        'type': tokens[0]
    }


def convert_print(_s, _l, tokens):
    print('convert_print', tokens)


def convert_object_identifier_type(_s, _l, _tokens):
    return {
        'type': 'OBJECT IDENTIFIER'
    }


def convert_bit_string_type(_s, _l, tokens):
    converted_type = {
        'type': 'BIT STRING'
    }

    named_bit_list = tokens.asList()[1]

    if named_bit_list:
        converted_type['named-bits'] = [
            tuple(named_bit) for named_bit in named_bit_list
        ]

    return converted_type


def convert_octet_string_type(_s, _l, _tokens):
    return {
        'type': 'OCTET STRING'
    }


def convert_ia5_string_type(_s, _l, _tokens):
    return {
        'type': 'IA5String'
    }


def convert_any_defined_by_type(_s, _l, tokens):
    return {
        'type': 'ANY DEFINED BY',
        'value': tokens[1],
        'choices': {}
    }


def convert_null_type(_s, _l, _tokens):
    return {
        'type': 'NULL'
    }


def convert_boolean_type(_s, _l, _tokens):
    return {
        'type': 'BOOLEAN'
    }


def convert_type(tokens):
    converted_type, constraints = tokens

    restricted_to = []

    for constraint_tokens in constraints:
        if isinstance(constraint_tokens, ParseResults):
            constraint_tokens = constraint_tokens.asList()

        if constraint_tokens == '...':
            restricted_to.append(EXTENSION_MARKER)
        elif len(constraint_tokens) == 1:
            if not isinstance(constraint_tokens[0], dict):
                restricted_to.append(convert_number(constraint_tokens[0]))
            elif 'size' in constraint_tokens[0]:
                converted_type.update(constraint_tokens[0])
            elif 'from' in constraint_tokens[0]:
                converted_type.update(constraint_tokens[0])
            elif 'with-components' in constraint_tokens[0]:
                converted_type.update(constraint_tokens[0])

    if '{' in restricted_to:
        restricted_to = []

    if restricted_to:
        converted_type['restricted-to'] = restricted_to

    types = [
        'BIT STRING',
        'OCTET STRING',
        'IA5String',
        'VisibleString',
        'UTF8String',
        'NumericString',
        'PrintableString'
    ]

    if converted_type['type'] in types:
        size = convert_size(constraints)

        if size:
            converted_type['size'] = size

    if '&' in converted_type['type']:
        converted_type['table'] = convert_table(tokens.asList()[1:])

    return converted_type


def convert_bstring(_s, _l, tokens):
    return '0b' + re.sub(r"[\sB']", '', tokens[0])


def convert_hstring(_s, _l, tokens):
    return '0x' + re.sub(r"[\sH']", '', tokens[0]).lower()


def convert_bit_string_value(tokens):
    value = tokens[0]

    if value == 'IdentifierList':
        value = value[:]
    elif isinstance(value, str):
        value = value
    else:
        value = None

    return value


def convert_value(tokens, type_=None):
    if type_ == 'INTEGER':
        value = int(tokens[0])
    elif type_ == 'OBJECT IDENTIFIER':
        value = []

        for value_tokens in tokens:
            if len(value_tokens) == 2:
                value.append((value_tokens[0], int(value_tokens[1])))
            else:
                value.append(convert_number(value_tokens[0]))
    elif type_ == 'BOOLEAN':
        value = (tokens[0] == 'TRUE')
    elif tokens[0] == 'BitStringValue':
        value = convert_bit_string_value(tokens[0])
    elif isinstance(tokens[0], str):
        value = convert_number(tokens[0])
    elif isinstance(tokens[0], int):
        value = tokens[0]
    else:
        value = None

    return value


def convert_parameterized_object_set_assignment(_s, _l, tokens):
    members = []

    try:
        for member_tokens in tokens[4].asList():
            if len(member_tokens[0]) == 1:
                member = member_tokens[0][0]
            else:
                member = {}

                for item_tokens in member_tokens[0]:
                    name = item_tokens[0]
                    value = item_tokens[1][0]

                    if isinstance(value, Tokens):
                        value = value[0]
                    member[name] = convert_number(value)

            members.append(member)
    except IndexError:
        pass

    converted_type = {
        'class': tokens[1],
        'members': members
    }

    return ('parameterized-object-set-assignment',
            tokens[0],
            converted_type)


def convert_parameterized_object_assignment(_s, _l, tokens):
    type_ = tokens[1]

    converted_type = {
        'type': type_,
        'value': None
    }

    return ('parameterized-object-assignment',
            tokens[0],
            converted_type)


def convert_parameterized_object_class_assignment(_s, _l, tokens):
    members = []

    for member in tokens[3]:
        if member[0][1].islower():
            converted_member = member[1][0]

            if isinstance(converted_member, Tokens):
                converted_member = converted_member[0]
        else:
            converted_member = {'type': 'OpenType'}

        converted_member['name'] = member[0]

        members.append(converted_member)

    converted_type = {
        'members': members
    }

    return ('parameterized-object-class-assignment',
            tokens[0],
            converted_type)


def convert_parameterized_type_assignment(_s, _l, tokens):
    tokens = tokens.asList()
    converted_type = convert_type(tokens[3])

    try:
        tag = convert_tag(tokens[2])
    except ValueError:
        tag = None

    if tag:
        converted_type['tag'] = tag

    return ('parameterized-type-assignment',
            tokens[0],
            converted_type)


def convert_parameterized_value_assignment(_s, _l, tokens):
    type_ = tokens[1][0][0]

    if isinstance(type_, Tokens):
        type_ = type_[0]
    elif isinstance(type_, dict):
        type_ = type_['type']

    converted_type = {
        'type': type_,
        'value': convert_value(tokens[2], type_)
    }

    return ('parameterized-value-assignment',
            tokens[0],
            converted_type)


def convert_imports(_s, _l, tokens):
    tokens = tokens.asList()
    imports = {}

    if tokens:
        for from_tokens in tokens:
            from_name = from_tokens[2]
            LOGGER.debug("Converting imports from '%s'.", from_name)
            imports[from_name] = from_tokens[0]

    return {'imports': imports}


def convert_assignment_list(_s, _l, tokens):
    types = {}
    values = {}
    object_classes = {}
    object_sets = {}

    for kind, name, value in tokens:
        if kind == 'parameterized-object-set-assignment':
            if name in object_sets:
                LOGGER.warning("Object set '%s' already defined.", name)

            object_sets[name] = value
        elif kind == 'parameterized-object-assignment':
            if name in values:
                LOGGER.warning("Object '%s' already defined.", name)

            values[name] = value
        elif kind == 'parameterized-object-class-assignment':
            if name in object_classes:
                LOGGER.warning("Object class '%s' already defined.", name)

            object_classes[name] = value
        elif kind == 'parameterized-type-assignment':
            if name in types:
                LOGGER.warning("Type '%s' already defined.", name)

            types[name] = value
        elif kind == 'parameterized-value-assignment':
            if name in values:
                LOGGER.warning("Value '%s' already defined.", name)

            values[name] = value
        else:
            raise InternalParserError(
                'Unrecognized assignment kind {}.'.format(kind))

    return {
        'types': types,
        'values': values,
        'object-classes': object_classes,
        'object-sets': object_sets
    }


def convert_module_body(_s, _l, tokens):
    return merge_dicts(tokens)


def convert_module_definition(_s, _l, tokens):
    tokens = tokens.asList()
    module = tokens[1][0]
    module['extensibility-implied'] = (tokens[0][3] != [])

    if tokens[0][2]:
        module['tags'] = tokens[0][2][0]

    return {tokens[0][0]: module}


def convert_specification(_s, _l, tokens):
    return merge_dicts(tokens)


def create_grammar():
    """Return the ASN.1 grammar as Pyparsing objects.

    """

    # Keywords.
    SEQUENCE = Keyword('SEQUENCE').setName('SEQUENCE')
    CHOICE = Keyword('CHOICE').setName('CHOICE')
    ENUMERATED = Keyword('ENUMERATED').setName('ENUMERATED')
    DEFINITIONS = Keyword('DEFINITIONS').setName('DEFINITIONS')
    BEGIN = Keyword('BEGIN').setName('BEGIN')
    END = Keyword('END').setName('END')
    AUTOMATIC = Keyword('AUTOMATIC').setName('AUTOMATIC')
    TAGS = Keyword('TAGS').setName('TAGS')
    OPTIONAL = Keyword('OPTIONAL').setName('OPTIONAL')
    OF = Keyword('OF').setName('OF')
    SIZE = Keyword('SIZE').setName('SIZE')
    INTEGER = Keyword('INTEGER').setName('INTEGER')
    REAL = Keyword('REAL').setName('REAL')
    BIT_STRING = Keyword('BIT STRING').setName('BIT STRING')
    OCTET_STRING = Keyword('OCTET STRING').setName('OCTET STRING')
    DEFAULT = Keyword('DEFAULT').setName('DEFAULT')
    IMPORTS = Keyword('IMPORTS').setName('IMPORTS')
    EXPORTS = Keyword('EXPORTS').setName('EXPORTS')
    FROM = Keyword('FROM').setName('FROM')
    CONTAINING = Keyword('CONTAINING').setName('CONTAINING')
    ENCODED_BY = Keyword('ENCODED_BY').setName('ENCODED_BY')
    IMPLICIT = Keyword('IMPLICIT').setName('IMPLICIT')
    EXPLICIT = Keyword('EXPLICIT').setName('EXPLICIT')
    OBJECT_IDENTIFIER = Keyword('OBJECT IDENTIFIER').setName('OBJECT IDENTIFIER')
    UNIVERSAL = Keyword('UNIVERSAL').setName('UNIVERSAL')
    APPLICATION = Keyword('APPLICATION').setName('APPLICATION')
    PRIVATE = Keyword('PRIVATE').setName('PRIVATE')
    SET = Keyword('SET').setName('SET')
    ANY_DEFINED_BY = Keyword('ANY DEFINED BY').setName('ANY DEFINED BY')
    EXTENSIBILITY_IMPLIED = Keyword('EXTENSIBILITY IMPLIED').setName(
        'EXTENSIBILITY IMPLIED')
    BOOLEAN = Keyword('BOOLEAN').setName('BOOLEAN')
    TRUE = Keyword('TRUE').setName('TRUE')
    FALSE = Keyword('FALSE').setName('FALSE')
    CLASS = Keyword('CLASS').setName('CLASS')
    WITH_SYNTAX = Keyword('WITH SYNTAX').setName('WITH SYNTAX')
    UNIQUE = Keyword('UNIQUE').setName('UNIQUE')
    NULL = Keyword('NULL').setName('NULL')
    WITH_COMPONENT = Keyword('WITH COMPONENT').setName('WITH COMPONENT')
    WITH_COMPONENTS = Keyword('WITH COMPONENTS').setName('WITH COMPONENTS')
    COMPONENTS_OF = Keyword('COMPONENTS OF').setName('COMPONENTS OF')
    PRESENT = Keyword('PRESENT').setName('PRESENT')
    ABSENT = Keyword('ABSENT').setName('ABSENT')
    ALL = Keyword('ALL').setName('ALL')
    MIN = Keyword('MIN').setName('MIN')
    MAX = Keyword('MAX').setName('MAX')
    INCLUDES = Keyword('INCLUDES').setName('INCLUDES')
    PATTERN = Keyword('PATTERN').setName('PATTERN')
    CONSTRAINED_BY = Keyword('CONSTRAINED BY').setName('CONSTRAINED BY')
    UNION = Keyword('UNION').setName('UNION')
    INTERSECTION = Keyword('INTERSECTION').setName('INTERSECTION')
    PLUS_INFINITY = Keyword('PLUS-INFINITY').setName('PLUS-INFINITY')
    MINUS_INFINITY = Keyword('MINUS-INFINITY').setName('MINUS-INFINITY')
    BMPString = Keyword('BMPString').setName('BMPString')
    GeneralString = Keyword('GeneralString').setName('GeneralString')
    GraphicString = Keyword('GraphicString').setName('GraphicString')
    IA5String = Keyword('IA5String').setName('IA5String')
    ISO646String = Keyword('ISO646String').setName('ISO646String')
    NumericString = Keyword('NumericString').setName('NumericString')
    PrintableString = Keyword('PrintableString').setName('PrintableString')
    TeletexString = Keyword('TeletexString').setName('TeletexString')
    UTCTime = Keyword('UTCTime').setName('UTCTime')
    GeneralizedTime = Keyword('GeneralizedTime').setName('GeneralizedTime')
    T61String = Keyword('T61String').setName('T61String')
    UniversalString = Keyword('UniversalString').setName('UniversalString')
    UTF8String = Keyword('UTF8String').setName('UTF8String')
    VideotexString = Keyword('VideotexString').setName('VideotexString')
    VisibleString = Keyword('VisibleString').setName('VisibleString')
    CHARACTER_STRING = Keyword('CHARACTER STRING').setName('CHARACTER STRING')

    # Various literals.
    word = Word(printables, excludeChars=',(){}[].:=;"|').setName('word')
    identifier = Regex(r'[a-z][a-zA-Z0-9-]*').setName('identifier')
    assign = Literal('::=').setName('::=')
    left_parenthesis = Literal('(')
    right_parenthesis = Literal(')')
    left_brace = Literal('{')
    right_brace = Literal('}')
    left_bracket = Literal('[')
    right_bracket = Literal(']')
    left_version_brackets = Literal('[[')
    right_version_brackets = Literal(']]')
    colon = Literal(':')
    semi_colon = Literal(';')
    dot = Literal('.')
    range_separator = Literal('..')
    ellipsis = Literal('...')
    pipe = Literal('|')
    caret = Literal('^')
    comma = Literal(',')
    at = Literal('@')
    exclamation_mark = Literal('!')
    integer = Word(nums + '-')
    real_number = Regex(r'[+-]?\d+\.?\d*([eE][+-]?\d+)?')
    bstring = Regex(r"'[01\s]*'B")
    hstring = Regex(r"'[0-9A-F\s]*'H")
    cstring = QuotedString('"')
    number = (Word(nums).setName('number') + ~dot)
    number = Word(printables, excludeChars=',(){}[].:=;"|').setName('number')
    ampersand = Literal('&')
    less_than = Literal('<')

    reserved_words = Regex(r'(END|SEQUENCE|ENUMERATED)(\s|$)')

    # Forward declarations.
    value = Forward()
    type_ = Forward()
    object_ = Forward()
    object_set = Forward()
    primitive_field_name = Forward()
    constraint = Forward()
    element_set_spec = Forward()
    token_or_group_spec = Forward()
    value_reference = Forward().setName('valuereference')
    type_reference = Forward().setName('typereference')
    value_set = Forward().setName('"valueSet" not implemented')
    named_type = Forward()
    root_element_set_spec = Forward()
    defined_object_set = Forward()
    syntax_list = Forward()
    object_from_object = Forward()
    object_set_from_objects = Forward()
    defined_value = Forward().setName('DefinedValue')
    component_type_lists = Forward()
    extension_and_exception = Forward()
    optional_extension_marker = Forward()
    additional_element_set_spec = Forward()
    reference = Forward()
    defined_object_class = Forward()
    defined_type = Forward()
    module_reference = Forward()
    external_type_reference = Forward()
    external_value_reference = Forward()
    simple_defined_type = Forward()
    defined_object = Forward()
    referenced_value = Forward()
    builtin_value = Forward()
    named_value = Forward()
    sequence_value = Forward()
    signed_number = Forward()
    name_and_number_form = Forward()
    number_form = Forward().setName('numberForm')
    definitive_number_form = Forward().setName('definitiveNumberForm')
    version_number = Forward()
    union_mark = Forward()
    named_number = Forward()
    size_constraint = Forward()

    value_field_reference = Combine(ampersand + value_reference)
    type_field_reference = Combine(ampersand + type_reference)

    # ToDo: Remove size_paren as they are a workaround for
    #       SEQUENCE/SET OF.
    size_paren = (Suppress(Optional(left_parenthesis))
                  + size_constraint
                  + Suppress(Optional(right_parenthesis)))

    class_number = (number | defined_value).setName('ClassNumber')
    tag = Group(Optional(Suppress(left_bracket)
                         - Group(Optional(UNIVERSAL
                                          | APPLICATION
                                          | PRIVATE)
                                 + class_number)
                         - Suppress(right_bracket)
                         + Group(Optional(IMPLICIT | EXPLICIT))))

    any_defined_by_type = (ANY_DEFINED_BY + word)
    any_defined_by_type.setName('ANY DEFINED BY')

    identifier_list = delimitedList(identifier)

    # X.683: 8. Parameterized assignments
    dummy_reference = reference
    dummy_governor = dummy_reference
    governor = (type_ | defined_object_class)
    param_governor = (governor | dummy_governor)
    parameter = (Optional(param_governor + colon) + dummy_reference)
    parameter_list = Suppress(Optional(left_brace
                                       + delimitedList(parameter)
                                       + right_brace))

    # X.683: 9. Referencing parameterized definitions
    actual_parameter = Group(type_
                             | value
                             | value_set
                             | defined_object_class
                             | object_
                             | object_set)
    actual_parameter_list = Group(Suppress(left_brace)
                                  + delimitedList(actual_parameter)
                                  + Suppress(right_brace))
    parameterized_object = (defined_object + actual_parameter_list)
    parameterized_object_set = (defined_object_set + actual_parameter_list)
    parameterized_object_class = (defined_object_class + actual_parameter_list)
    parameterized_value_set_type = (simple_defined_type
                                    + actual_parameter_list)
    simple_defined_value = (external_value_reference
                            | value_reference)
    parameterized_value = (simple_defined_value
                           + actual_parameter_list)
    simple_defined_type <<= (external_type_reference
                             | type_reference)
    parameterized_type = (simple_defined_type
                          + actual_parameter_list)
    parameterized_reference = (reference + Optional(left_brace + right_brace))

    # X.682: 11. Contents constraints
    contents_constraint = ((CONTAINING + type_)
                           | (ENCODED_BY + value)
                           | (CONTAINING + type_ + ENCODED_BY + value))

    # X.682: 10. Table constraints, including component relation constraints
    level = OneOrMore(dot)
    component_id_list = identifier
    at_notation = (Suppress(at)
                   - (component_id_list
                      | Combine(level + component_id_list)))
    component_relation_constraint = (left_brace
                                     + Group(Group(defined_object_set))
                                     + right_brace
                                     + left_brace
                                     - Group(delimitedList(at_notation))
                                     - right_brace)
    component_relation_constraint.setName('"{"')
    simple_table_constraint = object_set
    table_constraint = (component_relation_constraint
                        | simple_table_constraint)

    # X.682: 9. User-defined constants
    user_defined_constraint_parameter = ((governor
                                          + colon
                                          + (value
                                             | value_set
                                             | object_
                                             | object_set))
                                         | type_
                                         | defined_object_class)
    user_defined_constraint = (CONSTRAINED_BY
                               - left_brace
                               - Optional(delimitedList(
                                   user_defined_constraint_parameter))
                               - right_brace)
    user_defined_constraint.setName('CONSTRAINED_BY')

    # X.682: 8. General constraint specification
    general_constraint = (user_defined_constraint
                          | table_constraint
                          | contents_constraint)

    # X.681: 7. ASN.1 lexical items
    object_set_reference = type_reference
    value_set_field_reference = NoMatch().setName(
        '"valueSetFieldReference" not implemented')
    object_field_reference = NoMatch().setName(
        '"objectFieldReference" not implemented')
    object_set_field_reference = NoMatch().setName(
        '"objectSetFieldReference" not implemented')
    object_class_reference = (NotAny(reserved_words)
                              + Regex(r'[A-Z][A-Z0-9-]*'))
    object_reference = value_reference

    # X.681: 8. Referencing definitions
    external_object_set_reference = NoMatch().setName(
        '"externalObjectSetReference" not implemented')
    defined_object_set <<= (external_object_set_reference
                            | object_set_reference)
    defined_object <<= NoMatch().setName('"definedObject" not implemented')
    defined_object_class <<= object_class_reference

    # X.681: 9. Information object class definition and assignment
    field_name = primitive_field_name
    primitive_field_name <<= (type_field_reference
                              | value_field_reference
                              | value_set_field_reference
                              | object_field_reference
                              | object_set_field_reference)
    object_set_field_spec = NoMatch().setName('"objectSetFieldSpec" not implemented')
    object_field_spec = NoMatch().setName('"objectFieldSpec" not implemented')
    variable_type_value_set_field_spec = NoMatch().setName(
        '"variableTypeValueSetFieldSpec" not implemented')
    fixed_type_value_set_field_spec = NoMatch().setName(
        '"fixedTypeValueSetFieldSpec" not implemented')
    variable_type_value_field_spec = NoMatch().setName(
        '"variableTypeValueFieldSpec" not implemented')
    fixed_type_value_field_spec = (value_field_reference
                                   + type_
                                   + Optional(UNIQUE)
                                   + Optional(OPTIONAL
                                              | (DEFAULT - value)))
    type_field_spec = (type_field_reference
                       + Optional(OPTIONAL
                                  | (DEFAULT - type_)))
    field_spec = Group(type_field_spec
                       | fixed_type_value_field_spec
                       | variable_type_value_field_spec
                       | fixed_type_value_set_field_spec
                       | variable_type_value_set_field_spec
                       | object_field_spec
                       | object_set_field_spec)
    with_syntax_spec = (WITH_SYNTAX - syntax_list)
    object_class_defn = (CLASS
                         - Suppress(left_brace)
                         - Group(delimitedList(field_spec))
                         - Suppress(right_brace)
                         - Optional(with_syntax_spec))
    object_class = (object_class_defn
                    # | defined_object_class
                    | parameterized_object_class)
    parameterized_object_class_assignment = (object_class_reference
                                             + parameter_list
                                             + assign
                                             + object_class)

    # X.681: 10. Syntax list
    literal = (word | comma)
    required_token = (literal | primitive_field_name)
    optional_group = (left_bracket
                      + OneOrMore(token_or_group_spec)
                      + right_bracket)
    token_or_group_spec <<= (required_token | optional_group)
    syntax_list <<= (left_brace
                     + OneOrMore(token_or_group_spec)
                     + right_brace)

    # X.681: 11. Information object definition and assignment
    setting = (type_ | value | value_set | object_ | object_set | QuotedString('"'))
    field_setting = Group(primitive_field_name + setting)
    default_syntax = (Suppress(left_brace)
                      + delimitedList(field_setting)
                      + Suppress(right_brace))
    defined_syntax = NoMatch().setName('"definedSyntax" not implemented')
    object_defn = Group(default_syntax | defined_syntax)
    object_ <<= (defined_object
                 | object_defn
                 | object_from_object
                 | parameterized_object)
    parameterized_object_assignment = (object_reference
                                       + parameter_list
                                       + defined_object_class
                                       + Suppress(assign)
                                       + object_)

    # X.681: 12. Information object set definition and assignment
    object_set_elements = (object_
                           | defined_object_set
                           | object_set_from_objects
                           | parameterized_object_set)
    object_set_spec = ((root_element_set_spec
                        + Optional(comma
                                   + ellipsis
                                   + Optional(comma
                                              + additional_element_set_spec)))
                       | (ellipsis + Optional(comma + additional_element_set_spec)))
    object_set <<= (left_brace + Group(object_set_spec) + right_brace)
    object_set.setName('"{"')
    parameterized_object_set_assignment = (object_set_reference
                                           + parameter_list
                                           + defined_object_class
                                           - assign
                                           - object_set)

    # X.681: 13. Associated tables

    # X.681: 14. Notation for the object class field type
    fixed_type_field_val = (builtin_value | referenced_value)
    open_type_field_val = (type_ + colon + value)
    object_class_field_value = (open_type_field_val
                                | fixed_type_field_val)
    object_class_field_type = Combine(defined_object_class
                                      + dot
                                      + field_name)
    object_class_field_type.setName('ObjectClassFieldType')

    # X.681: 15. Information from objects
    object_set_from_objects <<= NoMatch().setName(
        '"objectSetFromObjects" not implemented')
    object_from_object <<= NoMatch().setName('"objectFromObject" not implemented')

    # X.680: 49. The exception identifier
    exception_spec = Optional(
        exclamation_mark
        + NoMatch().setName('"exceptionSpec" not implemented'))

    # X.680: 47. Subtype elements
    pattern_constraint = (PATTERN + value)
    value_constraint = constraint
    presence_constraint = (PRESENT | ABSENT | OPTIONAL)
    component_constraint = (Optional(value_constraint)
                            + Optional(presence_constraint))
    named_constraint = Group(identifier + component_constraint)
    type_constraints = delimitedList(named_constraint)
    full_specification = (left_brace + Group(type_constraints) + right_brace)
    partial_specification = (left_brace
                             + Group(ellipsis
                                     + Suppress(comma)
                                     + type_constraints)
                             + right_brace)
    single_type_constraint = constraint
    multiple_type_constraints = (full_specification | partial_specification)
    inner_type_constraints = ((WITH_COMPONENT - single_type_constraint)
                              | (WITH_COMPONENTS - multiple_type_constraints))
    permitted_alphabet = (FROM - constraint)
    type_constraint = type_
    size_constraint <<= (SIZE - Group(constraint))
    upper_end_value = (value | MAX)
    lower_end_value = (value | MIN)
    upper_endpoint = (Optional(less_than) + upper_end_value)
    lower_endpoint = (lower_end_value + Optional(less_than))
    value_range = (((Combine(integer + dot) + Suppress(range_separator))
                    | (integer + Suppress(range_separator))
                    | (lower_endpoint + Suppress(range_separator)))
                   - upper_endpoint)
    contained_subtype = (Optional(INCLUDES) + type_)
    single_value = value
    subtype_elements = (size_constraint
                        | permitted_alphabet
                        | value_range
                        | inner_type_constraints
                        | single_value
                        | pattern_constraint
                        | contained_subtype
                        | type_constraint)

    # X.680: 46. Element set specification
    union_mark <<= (pipe | UNION)
    intersection_mark = (caret | INTERSECTION)
    elements = Group(subtype_elements
                     | object_set_elements
                     | (left_parenthesis + element_set_spec + right_parenthesis))
    unions = delimitedList(elements, delim=(union_mark | intersection_mark))
    element_set_spec <<= unions
    root_element_set_spec <<= element_set_spec
    additional_element_set_spec <<= element_set_spec
    element_set_specs = (root_element_set_spec
                         + Optional(Suppress(comma) - ellipsis
                                    + Optional(Suppress(comma)
                                               - additional_element_set_spec)))

    # X.680: 45. Constrained types
    subtype_constraint = element_set_specs
    constraint_spec = (general_constraint
                       | subtype_constraint)
    constraint_spec.setName('one or more constraints')
    constraint <<= (Suppress(left_parenthesis)
                    - constraint_spec
                    - Suppress(right_parenthesis))

    # X.680: 40. Definition of unrestricted character string types
    unrestricted_character_string_type = CHARACTER_STRING
    unrestricted_character_string_value = NoMatch().setName(
        '"unrestrictedCharacterStringValue" not implemented')

    # X.680: 39. Canonical order of characters

    # X.680: 38. Specification of the ASN.1 module "ASN.1-CHARACTER-MODULE"

    # X.680: 37. Definition of restricted character string types
    group = number
    plane = number
    row = number
    cell = number
    quadruple = (left_brace
                 + group + comma
                 + plane + comma
                 + row + comma
                 + cell
                 + right_brace)
    table_column = number
    table_row = number
    tuple_ = (left_brace + table_column + comma + table_row + right_brace)
    chars_defn = (cstring | quadruple | tuple_ | defined_value)
    charsyms = delimitedList(chars_defn)
    character_string_list = (left_brace + charsyms + right_brace)
    restricted_character_string_value = (cstring
                                         | character_string_list
                                         | quadruple
                                         | tuple_)
    restricted_character_string_type = (BMPString
                                        | GeneralString
                                        | GraphicString
                                        | IA5String
                                        | ISO646String
                                        | NumericString
                                        | PrintableString
                                        | TeletexString
                                        | UTCTime
                                        | GeneralizedTime
                                        | T61String
                                        | UniversalString
                                        | UTF8String
                                        | VideotexString
                                        | VisibleString)

    # X.680: 36. Notation for character string types
    character_string_value = (restricted_character_string_value
                              | unrestricted_character_string_value)
    character_string_type = (restricted_character_string_type
                             | unrestricted_character_string_type)

    # X.680: 35. The character string types

    # X.680: 34. Notation for the external type
    # external_value = sequence_value

    # X.680: 33. Notation for embedded-pdv type
    # embedded_pdv_value = sequence_value

    # X.680: 32. Notation for relative object identifier type
    relative_oid_components = Group(number_form
                                    | name_and_number_form
                                    | defined_value)
    relative_oid_component_list = OneOrMore(relative_oid_components)
    relative_oid_value = (Suppress(left_brace)
                          + relative_oid_component_list
                          + Suppress(right_brace))

    # X.680: 31. Notation for object identifier type
    name_and_number_form <<= (identifier
                              + Suppress(left_parenthesis)
                              - number_form
                              - Suppress(right_parenthesis))
    number_form <<= (number | defined_value)
    name_form = identifier
    obj_id_components = Group(name_and_number_form
                              | defined_value
                              | number_form
                              | name_form)
    obj_id_components_list = OneOrMore(obj_id_components)
    object_identifier_value = ((Suppress(left_brace)
                                + obj_id_components_list
                                + Suppress(right_brace))
                               | (Suppress(left_brace)
                                  + defined_value
                                  + obj_id_components_list
                                  + Suppress(right_brace)))

    object_identifier_type = (OBJECT_IDENTIFIER
                              + Optional(left_parenthesis
                                         + delimitedList(word, delim='|')
                                         + right_parenthesis))
    object_identifier_type.setName('OBJECT IDENTIFIER')

    # X.680: 30. Notation for tagged types
    tagged_value = NoMatch()

    # X.680: 29. Notation for selection types

    # X.680: 28. Notation for the choice types
    alternative_type_list = delimitedList(named_type)
    extension_addition_alternatives_group = Group(left_version_brackets
                                                  + Suppress(version_number)
                                                  - Group(alternative_type_list)
                                                  - right_version_brackets)
    extension_addition_alternative = (extension_addition_alternatives_group
                                      | named_type)
    extension_addition_alternatives_list = delimitedList(extension_addition_alternative)
    extension_addition_alternatives = Optional(Suppress(comma)
                                               + extension_addition_alternatives_list)
    root_alternative_type_list = alternative_type_list
    alternative_type_lists = (root_alternative_type_list
                              + Optional(Suppress(comma)
                                         + extension_and_exception
                                         + extension_addition_alternatives
                                         + optional_extension_marker))
    choice_type = (CHOICE
                   - left_brace
                   + Group(alternative_type_lists)
                   - right_brace)
    choice_type.setName('CHOICE')
    choice_value = (identifier + colon + value)

    # X.680: 27. Notation for the set-of types
    # set_of_value = NoMatch()
    set_of_type = (SET
                   + Group(Optional(size_paren))
                   + OF
                   + Optional(Suppress(identifier))
                   - tag
                   - type_)
    set_of_type.setName('SET OF')

    # X.680: 26. Notation for the set types
    # set_value = NoMatch()
    set_type = (SET
                + left_brace
                + Group(Optional(component_type_lists
                                 | (extension_and_exception
                                    + optional_extension_marker)))
                - right_brace)
    set_type.setName('SET')

    # X.680: 25. Notation for the sequence-of types
    sequence_of_value = NoMatch()
    sequence_of_type = (SEQUENCE
                        + Group(Optional(size_paren))
                        + OF
                        + Optional(Suppress(identifier))
                        - tag
                        - type_)
    sequence_of_type.setName('SEQUENCE OF')

    # X.680: 24. Notation for the sequence types
    component_value_list = delimitedList(named_value)
    sequence_value <<= (left_brace
                        + Optional(component_value_list)
                        + right_brace)
    component_type = Group(named_type
                           + Group(Optional(OPTIONAL
                                            | (DEFAULT + value)))
                           | (COMPONENTS_OF - type_))
    version_number <<= Optional(number + Suppress(colon))
    extension_addition_group = Group(left_version_brackets
                                     + Suppress(version_number)
                                     + Group(delimitedList(component_type))
                                     + right_version_brackets)
    extension_and_exception <<= (ellipsis + Optional(exception_spec))
    extension_addition = (component_type | extension_addition_group)
    extension_addition_list = delimitedList(extension_addition)
    extension_additions = Optional(Suppress(comma) + extension_addition_list)
    extension_end_marker = (Suppress(comma) + ellipsis)
    optional_extension_marker <<= Optional(Suppress(comma) + ellipsis)
    component_type_list = delimitedList(component_type)
    root_component_type_list = component_type_list
    component_type_lists <<= ((root_component_type_list
                               + Optional(Suppress(comma)
                                          + extension_and_exception
                                          + extension_additions
                                          + ((extension_end_marker
                                              + Suppress(comma)
                                              + root_component_type_list)
                                             | optional_extension_marker)))
                              | (extension_and_exception
                                 + extension_additions
                                 + ((extension_end_marker
                                     + Suppress(comma)
                                     + root_component_type_list)
                                    | optional_extension_marker)))
    sequence_type = (SEQUENCE
                     - left_brace
                     + Group(Optional(component_type_lists
                                      | (extension_and_exception
                                         + optional_extension_marker)))
                     - right_brace)
    sequence_type.setName('SEQUENCE')

    # X.680: 23. Notation for the null type
    null_value = NULL
    null_type = NULL

    # X.680: 22. Notation for the octetstring type
    # octet_string_value = (bstring
    #                       | hstring
    #                       | (CONTAINING + value))
    octet_string_type = OCTET_STRING
    octet_string_type.setName('OCTET STRING')

    # X.680: 21. Notation for the bitstring type
    bit_string_type = (BIT_STRING
                       + Group(Optional(
                           Suppress(left_brace)
                           + delimitedList(Group(word
                                                 + Suppress(left_parenthesis)
                                                 + word
                                                 + Suppress(right_parenthesis)))
                           + Suppress(right_brace))))
    bit_string_type.setName('BIT STRING')
    bit_string_value = Tag('BitStringValue',
                           bstring
                           | hstring
                           | Tag('IdentifierList',
                                 Suppress(left_brace)
                                 + Optional(identifier_list)
                                 + Suppress(right_brace))
                           | (CONTAINING - value))

    # X.680: 20. Notation for the real type
    special_real_value = (PLUS_INFINITY
                          | MINUS_INFINITY)
    numeric_real_value = (real_number
                          | sequence_value)
    real_value = (numeric_real_value
                  | special_real_value)
    real_type = REAL
    real_type.setName('REAL')

    # X.680: 19. Notation for the enumerated type
    enumerated_value = identifier
    enumeration_item = (Group(named_number) | identifier)
    enumeration = delimitedList(enumeration_item)
    root_enumeration = enumeration
    additional_enumeration = enumeration
    enumerations = Group(Group(root_enumeration)
                         + Group(Optional(Group(Suppress(comma
                                                         - ellipsis
                                                         + exception_spec))
                                          + Optional(Suppress(comma)
                                                     - additional_enumeration))))
    enumerated_type = (ENUMERATED
                       - left_brace
                       + enumerations
                       - right_brace)
    enumerated_type.setName('ENUMERATED')

    # X.680: 18. Notation for the integer type
    integer_value = (signed_number | identifier)
    signed_number <<= Combine(Optional('-') + number)
    named_number <<= (identifier
                      + left_parenthesis
                      + (signed_number | defined_value)
                      + right_parenthesis)
    named_number_list = delimitedList(named_number)
    integer_type = (INTEGER
                    + Group(Optional(left_brace
                                     + named_number_list
                                     + right_brace)))
    integer_type.setName('INTEGER')

    # X.680: 17. Notation for boolean type
    boolean_type = BOOLEAN
    boolean_value = (TRUE | FALSE)

    # X.680: 16. Definition of types and values
    named_value <<= (identifier + value)
    referenced_value <<= NoMatch().setName('"referencedValue" not implemented')
    builtin_value <<= (bit_string_value
                       | boolean_value
                       | character_string_value
                       | choice_value
                       | relative_oid_value
                       | sequence_value
                       # | embedded_pdv_value
                       | enumerated_value
                       # | external_value
                       # | instance_of_value
                       | real_value
                       | integer_value
                       | null_value
                       | object_identifier_value
                       # | octet_string_value
                       | sequence_of_value
                       # | set_value
                       # | set_of_value
                       | tagged_value)
    value <<= Group(object_class_field_value)
    # | referenced_value
    # | builtin_value)
    named_type <<= Group(identifier
                         - tag
                         - type_)
    referenced_type = defined_type
    referenced_type.setName('ReferencedType')
    builtin_type = (choice_type
                    | integer_type
                    | null_type
                    | real_type
                    | bit_string_type
                    | octet_string_type
                    | enumerated_type
                    | sequence_of_type
                    | sequence_type
                    | object_class_field_type
                    | set_of_type
                    | set_type
                    | object_identifier_type
                    | boolean_type
                    | character_string_type)
    type_ <<= Group((builtin_type
                     | any_defined_by_type
                     | referenced_type).setName('Type')
                    + Group(ZeroOrMore(constraint)))

    # X.680: 15. Assigning types and values
    type_reference <<= (NotAny(reserved_words)
                        + Regex(r'[A-Z][a-zA-Z0-9-]*'))
    value_reference <<= Regex(r'[a-z][a-zA-Z0-9-]*')
    value_set <<= NoMatch().setName('"valueSet" not implemented')
    parameterized_type_assignment = (type_reference
                                     + parameter_list
                                     - assign
                                     - tag
                                     - type_)
    parameterized_value_assignment = (value_reference
                                      + parameter_list
                                      - Group(type_)
                                      - Suppress(assign)
                                      - value)

    # X.680: 14. Notation to support references to ASN.1 components

    # X.680: 13. Referencing type and value definitions
    external_value_reference <<= (module_reference
                                  + dot
                                  + value_reference)
    external_type_reference <<= (module_reference
                                 + dot
                                 + type_reference)
    defined_type <<= (external_type_reference
                      | parameterized_type
                      | parameterized_value_set_type
                      | type_reference)
    defined_value <<= (external_value_reference
                       | parameterized_value
                       | value_reference)

    # X.680: 12. Module definition
    module_reference <<= (NotAny(reserved_words)
                          + Regex(r'[A-Z][a-zA-Z0-9-]*').setName('modulereference'))
    assigned_identifier = Suppress(Optional(object_identifier_value
                                            | (defined_value + ~(comma | FROM))))
    global_module_reference = (module_reference + assigned_identifier)
    reference <<= (type_reference
                   | value_reference
                   | object_class_reference
                   | object_reference
                   | object_set_reference)
    symbol = (parameterized_reference
              | reference)
    symbol_list = Group(delimitedList(symbol))
    symbols_from_module = (symbol_list
                           + FROM
                           + global_module_reference)
    symbols_imported = OneOrMore(Group(symbols_from_module))
    imports = Optional(Suppress(IMPORTS)
                       - symbols_imported
                       - Suppress(semi_colon))
    symbols_exported = OneOrMore(symbol_list)
    exports = Suppress(Optional(EXPORTS
                                - (ALL | symbols_exported) + semi_colon))
    assignment = (parameterized_object_set_assignment
                  | parameterized_object_assignment
                  | parameterized_object_class_assignment
                  | parameterized_type_assignment
                  | parameterized_value_assignment)
    assignment_list = ZeroOrMore(assignment)
    module_body = (exports + imports + assignment_list)
    definitive_name_and_number_form = (identifier
                                       + Suppress(left_parenthesis)
                                       - definitive_number_form
                                       - Suppress(right_parenthesis))
    definitive_number_form <<= number
    definitive_obj_id_component = Group(definitive_name_and_number_form
                                        | name_form
                                        | definitive_number_form)
    definitive_obj_id_components_list = OneOrMore(definitive_obj_id_component)
    definitive_identifier = Group(Optional(Suppress(left_brace)
                                           - definitive_obj_id_components_list
                                           - Suppress(right_brace)))
    module_identifier = (module_reference
                         + definitive_identifier)
    tag_default = Group(Optional((AUTOMATIC | EXPLICIT | IMPLICIT) + TAGS))
    extension_default = Group(Optional(EXTENSIBILITY_IMPLIED))
    module_definition = (Group(module_identifier
                               - Suppress(DEFINITIONS)
                               + tag_default
                               + extension_default
                               - Suppress(assign)
                               - Suppress(BEGIN))
                         + Group(module_body)
                         - Suppress(END))

    # The whole specification.
    specification = OneOrMore(module_definition) + StringEnd()

    # Parse actions converting tokens to asn1tools representation.
    integer.setParseAction(convert_integer)
    signed_number.setParseAction(convert_integer)
    real_number.setParseAction(convert_real_number)
    bstring.setParseAction(convert_bstring)
    hstring.setParseAction(convert_hstring)
    value_range.setParseAction(convert_value_range)
    inner_type_constraints.setParseAction(convert_inner_type_constraints)
    size_constraint.setParseAction(convert_size_constraint)
    permitted_alphabet.setParseAction(convert_permitted_alphabet)
    constraint.setParseAction(convert_constraint)
    module_body.setParseAction(convert_module_body)
    specification.setParseAction(convert_specification)
    module_definition.setParseAction(convert_module_definition)
    assignment_list.setParseAction(convert_assignment_list)
    imports.setParseAction(convert_imports)
    parameterized_object_set_assignment.setParseAction(
        convert_parameterized_object_set_assignment)
    parameterized_object_assignment.setParseAction(
        convert_parameterized_object_assignment)
    parameterized_object_class_assignment.setParseAction(
        convert_parameterized_object_class_assignment)
    parameterized_type_assignment.setParseAction(
        convert_parameterized_type_assignment)
    parameterized_value_assignment.setParseAction(
        convert_parameterized_value_assignment)
    sequence_type.setParseAction(convert_sequence_type)
    sequence_of_type.setParseAction(convert_sequence_of_type)
    set_type.setParseAction(convert_set_type)
    set_of_type.setParseAction(convert_set_of_type)
    integer_type.setParseAction(convert_integer_type)
    real_type.setParseAction(convert_real_type)
    boolean_type.setParseAction(convert_boolean_type)
    bit_string_type.setParseAction(convert_bit_string_type)
    octet_string_type.setParseAction(convert_octet_string_type)
    null_type.setParseAction(convert_null_type)
    object_identifier_type.setParseAction(convert_object_identifier_type)
    enumerated_type.setParseAction(convert_enumerated_type)
    choice_type.setParseAction(convert_choice_type)
    defined_type.setParseAction(convert_defined_type)
    character_string_type.setParseAction(convert_keyword_type)
    object_class_field_type.setParseAction(convert_keyword_type)
    any_defined_by_type.setParseAction(convert_any_defined_by_type)

    return specification


def ignore_comments(string):
    """Ignore comments in given string by replacing them with spaces. This
    reduces the parsing time by roughly a factor of two.

    """

    re_replace = re.compile(r'[^\n]')

    return re.sub(r"--([\s\S]*?(--|\n))",
                  lambda mo: re_replace.sub(' ', mo.group(0)),
                  string)


def parse_string(string):
    """Parse given ASN.1 specification string and return a dictionary of
    its contents.

    The dictionary can later be compiled with
    :func:`~asn1tools.compile_dict()`.

    >>> with open('foo.asn') as fin:
    ...     foo = asn1tools.parse_string(fin.read())

    """

    try:
        parse_tree = Asn1Parser().parse(string, token_tree=True)
        modules = Transformer().transform(parse_tree)
    except tp.ParseError as e:
        raise ParseError("Invalid ASN.1 syntax at line {}, column {}: '{}'.".format(
            e.line,
            e.column,
            tp.markup_line(e.text, e.offset)))

    grammar = create_grammar()

    try:
        string = ignore_comments(string)
        tokens = grammar.parseString(string).asList()
    except (ParseException, ParseSyntaxException) as e:
        raise ParseError("Invalid ASN.1 syntax at line {}, column {}: '{}': {}.".format(
            e.lineno,
            e.column,
            e.markInputline(),
            e.msg))

    return tokens[0]


def parse_files(filenames, encoding='utf-8'):
    """Parse given ASN.1 specification file(s) and return a dictionary of
    its/their contents.

    The dictionary can later be compiled with
    :func:`~asn1tools.compile_dict()`.

    `encoding` is the text encoding. This argument is passed to the
    built-in function `open()`.

    >>> foo = asn1tools.parse_files('foo.asn')

    """

    if isinstance(filenames, str):
        filenames = [filenames]

    string = ''

    for filename in filenames:
        if sys.version_info[0] < 3:
            with open(filename, 'r') as fin:
                string += fin.read()
                string += '\n'
        else:
            with open(filename, 'r', encoding=encoding, errors='replace') as fin:
                string += fin.read()
                string += '\n'

    return parse_string(string)

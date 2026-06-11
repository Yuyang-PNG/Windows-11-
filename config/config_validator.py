import json
from typing import Dict, Any, Optional, List, Tuple


class ConfigValidator:
    """配置校验器 - 提供配置文件的格式校验和版本兼容性检查"""
    
    CURRENT_VERSION = "1.1"
    
    SCHEMAS = {
        'app_categories': {
            'required': ['version', 'categories'],
            'types': {
                'version': str,
                'description': str,
                'categories': dict,
                'last_updated': str
            },
            'nested': {
                'categories': {
                    'required': ['description', 'suggested_gpu', 'priority'],
                    'types': {
                        'description': str,
                        'suggested_gpu': str,
                        'priority': str,
                        'base_score': int,
                        'bonus_score': int,
                        'keywords': list,
                        'paths': list,
                        'window_titles': list,
                        'company_keywords': list
                    }
                }
            }
        },
        'scoring_rules': {
            'required': ['version', 'weights'],
            'types': {
                'version': str,
                'weights': dict,
                'category_base_scores': dict,
                'process_type_bonus': dict,
                'uptime_rules': list,
                'status_scores': dict
            },
            'nested': {
                'weights': {
                    'allowed_keys': ['cpu_weight', 'memory_weight', 'threads_weight', 
                                     'io_weight', 'uptime_weight', 'status_weight', 'type_weight'],
                    'value_range': (0, 100)
                },
                'uptime_rules': {
                    'required': ['condition', 'score'],
                    'types': {
                        'condition': str,
                        'score': int
                    }
                }
            }
        },
        'cross_factors': {
            'required': ['version'],
            'types': {
                'version': str,
                'factors': list,
                'system_adjustments': list
            },
            'nested': {
                'factors': {
                    'required': ['category', 'conditions', 'score_bonus'],
                    'types': {
                        'category': (str, list),
                        'conditions': list,
                        'logic': str,
                        'score_bonus': int,
                        'id': str
                    }
                },
                'system_adjustments': {
                    'required': ['condition', 'adjustment'],
                    'types': {
                        'condition': dict,
                        'adjustment': int
                    }
                }
            }
        }
    }

    @staticmethod
    def validate(config_type: str, config: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        校验配置文件
        
        Args:
            config_type: 配置类型 (app_categories, scoring_rules, cross_factors)
            config: 配置数据
            
        Returns:
            (是否有效, 错误消息列表)
        """
        errors = []
        
        if config_type not in ConfigValidator.SCHEMAS:
            errors.append(f"未知的配置类型: {config_type}")
            return False, errors
        
        schema = ConfigValidator.SCHEMAS[config_type]
        
        if not isinstance(config, dict):
            errors.append("配置必须是字典类型")
            return False, errors
        
        # 检查必填字段
        for required in schema.get('required', []):
            if required not in config:
                errors.append(f"缺少必填字段: {required}")
        
        # 检查字段类型
        for field, expected_type in schema.get('types', {}).items():
            if field in config:
                if not isinstance(config[field], expected_type):
                    errors.append(f"字段 {field} 类型错误，期望 {expected_type.__name__}，实际 {type(config[field]).__name__}")
        
        # 检查嵌套结构
        nested = schema.get('nested', {})
        for parent_field, child_schema in nested.items():
            if parent_field in config:
                parent_value = config[parent_field]
                
                if isinstance(parent_value, dict):
                    for child_key, child_value in parent_value.items():
                        errors.extend(ConfigValidator._validate_nested(
                            f"{parent_field}.{child_key}", child_value, child_schema
                        ))
                elif isinstance(parent_value, list):
                    for idx, item in enumerate(parent_value):
                        errors.extend(ConfigValidator._validate_nested(
                            f"{parent_field}[{idx}]", item, child_schema
                        ))
        
        # 检查版本兼容性
        version = config.get('version', 'unknown')
        compat_errors = ConfigValidator._check_version_compatibility(config_type, version)
        errors.extend(compat_errors)
        
        return len(errors) == 0, errors

    @staticmethod
    def _validate_nested(path: str, value: Any, schema: Dict) -> List[str]:
        """校验嵌套结构"""
        errors = []
        
        if not isinstance(value, dict):
            return errors
        
        # 检查必填字段
        for required in schema.get('required', []):
            if required not in value:
                errors.append(f"{path} 缺少必填字段: {required}")
        
        # 检查字段类型
        for field, expected_type in schema.get('types', {}).items():
            if field in value:
                if isinstance(expected_type, tuple):
                    if not any(isinstance(value[field], t) for t in expected_type):
                        type_names = ", ".join(t.__name__ for t in expected_type)
                        errors.append(f"{path}.{field} 类型错误，期望 {type_names}")
                elif not isinstance(value[field], expected_type):
                    errors.append(f"{path}.{field} 类型错误，期望 {expected_type.__name__}")
        
        # 检查允许的键
        allowed_keys = schema.get('allowed_keys')
        if allowed_keys:
            for key in value.keys():
                if key not in allowed_keys:
                    errors.append(f"{path} 包含不允许的键: {key}")
        
        # 检查值范围
        value_range = schema.get('value_range')
        if value_range and isinstance(value, (int, float)):
            min_val, max_val = value_range
            if value < min_val or value > max_val:
                errors.append(f"{path} 值超出范围 [{min_val}, {max_val}]")
        
        return errors

    @staticmethod
    def _check_version_compatibility(config_type: str, config_version: str) -> List[str]:
        """检查版本兼容性"""
        errors = []
        
        current_major, current_minor = map(int, ConfigValidator.CURRENT_VERSION.split('.'))
        try:
            config_major, config_minor = map(int, config_version.split('.'))
        except ValueError:
            errors.append(f"无效的版本格式: {config_version}")
            return errors
        
        if config_major > current_major:
            errors.append(f"配置版本 {config_version} 高于当前支持版本 {ConfigValidator.CURRENT_VERSION}")
        elif config_major < current_major:
            errors.append(f"配置版本 {config_version} 过旧，需要升级")
        
        return errors

    @staticmethod
    def fix_config(config_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        自动修复配置文件中的问题
        
        Args:
            config_type: 配置类型
            config: 配置数据
            
        Returns:
            修复后的配置
        """
        if config_type not in ConfigValidator.SCHEMAS:
            return config
        
        schema = ConfigValidator.SCHEMAS[config_type]
        fixed = config.copy() if isinstance(config, dict) else {}
        
        # 添加缺少的必填字段
        for required in schema.get('required', []):
            if required not in fixed:
                fixed[required] = ConfigValidator._get_default_value(required, config_type)
        
        # 修复字段类型
        for field, expected_type in schema.get('types', {}).items():
            if field in fixed:
                if isinstance(expected_type, tuple):
                    if not any(isinstance(fixed[field], t) for t in expected_type):
                        fixed[field] = ConfigValidator._convert_type(fixed[field], expected_type[0])
                elif not isinstance(fixed[field], expected_type):
                    fixed[field] = ConfigValidator._convert_type(fixed[field], expected_type)
        
        # 修复嵌套结构
        nested = schema.get('nested', {})
        for parent_field, child_schema in nested.items():
            if parent_field in fixed:
                parent_value = fixed[parent_field]
                
                if isinstance(parent_value, dict):
                    fixed[parent_field] = {
                        key: ConfigValidator._fix_nested_dict(value, child_schema)
                        for key, value in parent_value.items()
                    }
                elif isinstance(parent_value, list):
                    fixed[parent_field] = [
                        ConfigValidator._fix_nested_dict(item, child_schema) 
                        for item in parent_value
                    ]
        
        # 更新版本号
        fixed['version'] = ConfigValidator.CURRENT_VERSION
        
        return fixed

    @staticmethod
    def _get_default_value(field: str, config_type: str) -> Any:
        """获取字段的默认值"""
        defaults = {
            'version': ConfigValidator.CURRENT_VERSION,
            'description': '',
            'categories': {},
            'weights': {},
            'category_base_scores': {},
            'process_type_bonus': {},
            'uptime_rules': [],
            'status_scores': {},
            'factors': [],
            'system_adjustments': [],
            'last_updated': ''
        }
        return defaults.get(field, {})

    @staticmethod
    def _convert_type(value: Any, target_type: type) -> Any:
        """尝试转换类型"""
        try:
            if target_type == int:
                return int(value)
            elif target_type == float:
                return float(value)
            elif target_type == str:
                return str(value)
            elif target_type == list:
                return list(value) if hasattr(value, '__iter__') else []
            elif target_type == dict:
                return dict(value) if isinstance(value, (dict, list)) else {}
        except (ValueError, TypeError):
            pass
        return target_type()

    @staticmethod
    def _fix_nested_dict(data: dict, schema: dict) -> dict:
        """修复嵌套字典"""
        if not isinstance(data, dict):
            return {}
        
        fixed = data.copy()
        
        # 添加缺少的必填字段
        for required in schema.get('required', []):
            if required not in fixed:
                fixed[required] = {} if required == 'condition' else 0
        
        # 修复字段类型
        for field, expected_type in schema.get('types', {}).items():
            if field in fixed:
                if isinstance(expected_type, tuple):
                    if not any(isinstance(fixed[field], t) for t in expected_type):
                        fixed[field] = ConfigValidator._convert_type(fixed[field], expected_type[0])
                elif not isinstance(fixed[field], expected_type):
                    fixed[field] = ConfigValidator._convert_type(fixed[field], expected_type)
        
        # 限制允许的键
        allowed_keys = schema.get('allowed_keys')
        if allowed_keys:
            fixed = {k: v for k, v in fixed.items() if k in allowed_keys}
        
        return fixed

    @staticmethod
    def get_validation_report(config_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """获取详细的校验报告"""
        is_valid, errors = ConfigValidator.validate(config_type, config)
        
        return {
            'valid': is_valid,
            'errors': errors,
            'config_type': config_type,
            'config_version': config.get('version', 'unknown'),
            'current_version': ConfigValidator.CURRENT_VERSION,
            'field_count': len(config) if isinstance(config, dict) else 0
        }
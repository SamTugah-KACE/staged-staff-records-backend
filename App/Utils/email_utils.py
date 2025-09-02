import os
from jinja2 import Template

def parse_html_from_template(template_name: str, template_data: dict) -> str:
    """
    Parses an HTML or XML template and dynamically replaces placeholders.
    
    :param template_name: The name of the template file (HTML/XML)
    :param template_data: A dictionary of data to fill in the template placeholders.
    :return: The parsed HTML content as a string.
    """
    try:
        # Define template directory
        template_dir = os.path.join(os.path.dirname(__file__), '../templates')
        
        # Construct the full path to the template
        template_path = os.path.join(template_dir, template_name)
        
        # Check if template file exists
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"Template file not found: {template_path}")
        
        with open(template_path, encoding='utf-8') as file_:
            template_content = file_.read()
        
        # Create a Jinja2 template and render it with data
        template = Template(template_content)
        return template.render(**template_data)
        
    except Exception as e:
        # Log the error and return a fallback HTML
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to parse template '{template_name}': {e}")
        
        # Return a simple fallback HTML
        return f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>Welcome to {template_data.get('organization_name', 'Organization')}</h2>
            <p>Hello {template_data.get('employee_name', 'User')},</p>
            <p>Your account has been created successfully.</p>
            <p><strong>Username:</strong> {template_data.get('username', '')}</p>
            <p><strong>Password:</strong> {template_data.get('password', '')}</p>
            <p><a href="{template_data.get('login_url', '/signin')}">Click here to login</a></p>
        </body>
        </html>
        """

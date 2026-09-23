"""CLI commands for the application."""
import click
from app.extensions import db
from app.models.user import User


def register_commands(app):
    """Register CLI commands with the Flask app."""
    
    @app.cli.command()
    @click.argument('email')
    def make_admin(email):
        """Promote a user to admin by email."""
        user = User.query.filter_by(email=email.lower().strip()).first()
        if not user:
            click.echo(f'Error: No user found with email {email}')
            return
        
        if user.is_admin:
            click.echo(f'{user.owner_name} ({email}) is already an admin.')
            return
        
        user.is_admin = True
        db.session.commit()
        click.echo(f'✓ Success! {user.owner_name} ({email}) is now an admin.')

    @app.cli.command()
    @click.argument('email')
    def remove_admin(email):
        """Remove admin privileges from a user by email."""
        user = User.query.filter_by(email=email.lower().strip()).first()
        if not user:
            click.echo(f'Error: No user found with email {email}')
            return
        
        if not user.is_admin:
            click.echo(f'{user.owner_name} ({email}) is not an admin.')
            return
        
        user.is_admin = False
        db.session.commit()
        click.echo(f'✓ Admin privileges removed from {user.owner_name} ({email}).')

    @app.cli.command()
    def list_admins():
        """List all admin users."""
        admins = User.query.filter_by(is_admin=True).all()
        if not admins:
            click.echo('No admin users found.')
            return
        
        click.echo('Admin users:')
        for admin in admins:
            click.echo(f'  • {admin.owner_name} ({admin.email})')

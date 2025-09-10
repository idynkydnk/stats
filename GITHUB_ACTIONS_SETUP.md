# GitHub Actions Deployment to PythonAnywhere

This guide will help you set up automatic deployment from GitHub to PythonAnywhere using GitHub Actions.

## 🚀 Quick Setup

### Step 1: Get PythonAnywhere API Token

1. **Go to your PythonAnywhere dashboard**
2. **Click on "Account" tab**
3. **Scroll down to "API token" section**
4. **Click "Create new API token"**
5. **Copy the token** (you'll need it for GitHub secrets)

### Step 2: Set Up GitHub Secrets

1. **Go to your GitHub repository**
2. **Click on "Settings" tab**
3. **Click on "Secrets and variables" → "Actions"**
4. **Click "New repository secret"**
5. **Add these 3 secrets:**

   | Secret Name | Value | Description |
   |-------------|-------|-------------|
   | `PYTHONANYWHERE_USERNAME` | `idynkydnk` | Your PythonAnywhere username |
   | `PYTHONANYWHERE_API_TOKEN` | `your_api_token_here` | The API token from Step 1 |
   | `PYTHONANYWHERE_DOMAIN` | `idynkydnk.pythonanywhere.com` | Your PythonAnywhere domain |

### Step 3: Push to GitHub

The workflow is already set up! Just push your changes:

```bash
git add .
git commit -m "Add GitHub Actions deployment"
git push origin main
```

### Step 4: Monitor Deployment

1. **Go to your GitHub repository**
2. **Click on "Actions" tab**
3. **Watch the deployment workflow run**
4. **Check the logs** if there are any issues

## 🔧 How It Works

### Workflow Triggers
- **Automatic**: Every push to the `main` branch
- **Manual**: You can trigger it manually from the Actions tab

### What Happens During Deployment
1. **Code checkout**: Gets the latest code from GitHub
2. **Environment setup**: Sets up Python 3.10
3. **Dependencies**: Installs required packages
4. **Deployment**: Calls PythonAnywhere API to reload your web app
5. **Verification**: Checks if the site is responding

### Files Created
- `.github/workflows/deploy-to-pythonanywhere.yml` - GitHub Actions workflow
- `deploy_script.py` - Python script that handles the deployment

## 🛠️ Troubleshooting

### Common Issues

#### 1. API Token Issues
- **Error**: "Failed to reload web app"
- **Solution**: Check that your API token is correct and has the right permissions

#### 2. Domain Issues
- **Error**: "Could not verify deployment"
- **Solution**: Make sure your domain is correct (usually `username.pythonanywhere.com`)

#### 3. Workflow Not Triggering
- **Error**: Workflow doesn't run on push
- **Solution**: Check that you're pushing to the `main` branch

### Debugging Steps

1. **Check GitHub Actions logs**:
   - Go to Actions tab → Click on the failed workflow → Check the logs

2. **Verify secrets**:
   - Go to Settings → Secrets and variables → Actions
   - Make sure all 3 secrets are set correctly

3. **Test API token**:
   - You can test your API token manually:
   ```bash
   curl -X POST -H "Authorization: Token YOUR_TOKEN" \
        https://www.pythonanywhere.com/api/v0/user/idynkydnk/webapps/idynkydnk.pythonanywhere.com/reload/
   ```

## 🔄 Alternative: Scheduled Updates

If you prefer scheduled updates instead of real-time deployment:

1. **Remove the GitHub Actions workflow** (delete `.github/workflows/deploy-to-pythonanywhere.yml`)
2. **Use the scheduled task method** from the main README
3. **Set up a PythonAnywhere scheduled task** to run `auto_pull.sh` periodically

## 📋 Requirements

- **PythonAnywhere paid account** (API access requires paid plan)
- **GitHub repository** with Actions enabled
- **PythonAnywhere web app** already set up and running

## 🎯 Benefits

- ✅ **Real-time deployment** - Updates happen immediately when you push
- ✅ **No manual intervention** - Fully automated
- ✅ **Deployment history** - Track all deployments in GitHub Actions
- ✅ **Rollback capability** - Easy to revert to previous versions
- ✅ **Notification system** - Get notified of deployment status

## 🔐 Security Notes

- API tokens are stored securely in GitHub secrets
- Tokens are only used during deployment
- No sensitive data is exposed in logs
- Each deployment is logged and traceable

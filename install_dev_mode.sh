#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}Installing backend-test in Development Mode${NC}"
echo -e "${BLUE}============================================${NC}\n"

# Step 1: Get Tutor root
echo -e "${YELLOW}Step 1: Getting Tutor configuration root...${NC}"
TUTOR_ROOT=$(tutor config printroot)
if [ -z "$TUTOR_ROOT" ]; then
    echo -e "${RED}ERROR: Could not find Tutor root. Is Tutor installed?${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Tutor root: $TUTOR_ROOT${NC}\n"

# Step 2: Create docker-compose override directory
echo -e "${YELLOW}Step 2: Creating docker-compose override directory...${NC}"
OVERRIDE_DIR="$TUTOR_ROOT/env/dev"
mkdir -p "$OVERRIDE_DIR"
echo -e "${GREEN}✓ Directory created: $OVERRIDE_DIR${NC}\n"

# Step 3: Create docker-compose override file
echo -e "${YELLOW}Step 3: Creating docker-compose.override.yml...${NC}"
OVERRIDE_FILE="$OVERRIDE_DIR/docker-compose.override.yml"

# Backup existing override file if it exists
if [ -f "$OVERRIDE_FILE" ]; then
    BACKUP_FILE="$OVERRIDE_FILE.backup.$(date +%Y%m%d_%H%M%S)"
    echo -e "${YELLOW}  → Backing up existing override file to: $BACKUP_FILE${NC}"
    cp "$OVERRIDE_FILE" "$BACKUP_FILE"
fi

# Create the override file (remove version as it's obsolete in newer docker-compose)
cat > "$OVERRIDE_FILE" << EOF
services:
  lms:
    volumes:
      - $SCRIPT_DIR:/openedx/backend-test
  cms:
    volumes:
      - $SCRIPT_DIR:/openedx/backend-test
EOF

echo -e "${GREEN}✓ Override file created: $OVERRIDE_FILE${NC}"
echo -e "${GREEN}  → Mounting: $SCRIPT_DIR${NC}"
echo -e "${GREEN}  → To: /openedx/backend-test (inside containers)${NC}\n"

# Step 4: Stop and start containers to pick up new volume mounts
echo -e "${YELLOW}Step 4: Stopping containers...${NC}"
tutor dev stop lms cms
echo -e "${GREEN}✓ Containers stopped${NC}"

echo -e "${YELLOW}Starting containers with new mounts...${NC}"
echo -e "${YELLOW}  This may take a minute...${NC}"
tutor dev start -d lms cms
echo -e "${GREEN}✓ Containers started${NC}\n"

# Wait a bit for containers to be fully ready
echo -e "${YELLOW}Waiting for containers to be ready...${NC}"
sleep 5
echo -e "${GREEN}✓ Ready${NC}\n"

# Step 5: Verify mount
echo -e "${YELLOW}Step 5: Verifying mount inside container...${NC}"
if tutor dev exec lms ls /openedx/backend-test/pyproject.toml > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Mount verified successfully${NC}\n"
else
    echo -e "${RED}ERROR: Mount verification failed. Directory not accessible inside container.${NC}"
    exit 1
fi

# Step 6: Uninstall existing package if installed
echo -e "${YELLOW}Step 6: Checking for existing backend-test installation...${NC}"
if tutor dev exec lms pip show backend-test > /dev/null 2>&1; then
    echo -e "${YELLOW}  → Found existing installation, uninstalling...${NC}"
    tutor dev exec lms pip uninstall backend-test -y
    echo -e "${GREEN}✓ Existing package uninstalled${NC}\n"
else
    echo -e "${GREEN}✓ No existing installation found${NC}\n"
fi

# Step 7: Install in editable mode
echo -e "${YELLOW}Step 7: Installing package in editable/development mode...${NC}"
tutor dev exec lms pip install -e /openedx/backend-test
echo -e "${GREEN}✓ Package installed in editable mode${NC}\n"

# Step 8: Verify installation
echo -e "${YELLOW}Step 8: Verifying installation...${NC}"
PACKAGE_INFO=$(tutor dev exec lms pip show backend-test 2>&1)
if echo "$PACKAGE_INFO" | grep -q "Location: /openedx/backend-test"; then
    echo -e "${GREEN}✓ Package installed successfully in editable mode${NC}"
    echo -e "${GREEN}  Location: /openedx/backend-test${NC}\n"
else
    echo -e "${RED}ERROR: Package not installed correctly${NC}"
    echo "$PACKAGE_INFO"
    exit 1
fi

# Step 9: Verify management command
echo -e "${YELLOW}Step 9: Verifying management command is available...${NC}"
if tutor dev exec lms python manage.py help reset_course_progress > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Management command 'reset_course_progress' is available${NC}\n"
else
    echo -e "${RED}ERROR: Management command not found${NC}"
    exit 1
fi

# Success summary
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}✓ Installation Complete!${NC}"
echo -e "${GREEN}============================================${NC}\n"

echo -e "${BLUE}Summary:${NC}"
echo -e "  • Package mounted from: ${GREEN}$SCRIPT_DIR${NC}"
echo -e "  • Container path: ${GREEN}/openedx/backend-test${NC}"
echo -e "  • Mode: ${GREEN}Editable (development)${NC}"
echo -e "  • Changes to Python files will be immediately available"
echo ""

echo -e "${BLUE}Usage:${NC}"
echo -e "  # Run the management command:"
echo -e "  ${GREEN}tutor dev exec lms python manage.py lms reset_course_progress <username> <course_key> --confirm${NC}"
echo ""
echo -e "  # Dry run to preview:"
echo -e "  ${GREEN}tutor dev exec lms python manage.py lms reset_course_progress <username> <course_key> --dry-run${NC}"
echo ""

echo -e "${BLUE}To uninstall:${NC}"
echo -e "  ${GREEN}tutor dev exec lms pip uninstall backend-test -y${NC}"
echo ""

echo -e "${BLUE}To reinstall after making changes (usually not needed):${NC}"
echo -e "  ${GREEN}./install_dev_mode.sh${NC}"
echo ""

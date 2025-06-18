package list.report.controller;

import list.report.dto.IndustryReportItem;
import list.report.service.IndustryService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/reports")
public class IndustryController {

    private final IndustryService industryService;

    @Autowired
    public IndustryController(IndustryService industryService){
        this.industryService = industryService;
    }

    @GetMapping("/industry")
    public List<IndustryReportItem> getIndustry(){
        return industryService.fetchIndustryReport();
    }
}

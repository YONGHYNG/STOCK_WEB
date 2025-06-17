package list.community.controller;

import list.community.service.ComService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.io.IOException;
import java.util.List;

@RestController
@RequestMapping("/api/community")
@CrossOrigin(origins = "http://localhost:3000")
public class ComController {

    @Autowired
    private ComService comService;

    @GetMapping("/best")
    public List<String> getBestTitles() throws IOException {
        return comService.getBestTitles();
    }

}
